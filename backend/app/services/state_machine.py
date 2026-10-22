"""Ticket state machine — 7 状态，按新流程定义流转规则与操作权限。

状态：
  pending    待受理（初始）
  open       处理中
  resolved   已处理
  on_hold    暂缓处理
  archived   已归档（终态）
  returned   已退回
  cancelled  已撤销（终态）

操作权限：
  分派(pending→open)                                → 部门对接人
  已处理(open→resolved)、暂缓(open→on_hold)          → 处理人
  确认(on_hold→resolved)                            → 处理人
  归档(resolved→archived)                            → 客服团队
  退回(pending/open/on_hold/resolved→上一状态)       → 对应处理人

V0.86 改造（状态流转执行收口）后，本模块同时是状态流转的**唯一执行入口**：
  - 规则：TRANSITIONS / STATES_REQUIRE_REASON_FROM / TERMINAL_STATES / 业务约束改写
  - 权限：check_transition_permission（HTTP 权限矩阵的唯一定义处）
  - 执行：apply_transition —— 校验 → 权限 → reason → 状态副作用 → 写 Flow Log
任何写 ticket.state 的路径（单条 PATCH、batch-update、文章回复、建单/即时办结）
都必须经过 apply_transition / apply_initial_state。
"""

from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ForbiddenError, StateTransitionError
from app.models.group import SkillGroup, UserSkillGroup
from app.models.ticket import Ticket, TicketStateLog
from app.services.callback_policy import resolve_callback_required
from app.models.user import User

# 状态的中文展示名（错误信息 / 导出 / allowed_actions label 共用）
STATE_LABELS: dict[str, str] = {
    "pending": "待受理", "open": "处理中", "resolved": "已处理",
    "on_hold": "暂缓处理", "returned": "退回",
    "archived": "已归档", "cancelled": "已撤销",
}

# "曾退回"按业务动作记录；open→pending 也可表示转派，不能只看状态边。
RETURN_ACTIONS = {"return", "reopen"}

# 8 状态流转规则：{from_state: [to_state, ...]}
TRANSITIONS: dict[str, list[str]] = {
    # None 是建单的初始态。允许 None → pending（默认）、None → archived（即时办结咨询）
    "pending": ["open", "cancelled", "returned"],
    "open": ["resolved", "on_hold", "pending", "cancelled"],
    "on_hold": ["resolved", "open", "cancelled"],
    "resolved": ["archived", "open", "on_hold"],
    "returned": ["pending", "cancelled"],
    # 终态
    "archived": [],
    "cancelled": [],
}


def validate_initial_state(to_state: str) -> None:
    """校验建单时的初始状态。None → pending（默认）、None → archived（即时办结咨询）。"""
    if to_state not in {"pending", "archived"}:
        raise StateTransitionError(None, to_state)

# 需要填原因的目标状态：退回 / 暂缓 / 撤销
# 非 pending 状态退回时目标为「上一状态」；pending 退回时目标为 returned
STATES_REQUIRE_REASON_FROM: dict[str, set[str]] = {
    "pending": {"open", "on_hold", "resolved"},  # 处理中/暂缓/已处理 退回至待受理需原因
    "open": {"on_hold", "resolved"},             # 暂缓/已处理 退回至处理中需原因
    "on_hold": {"open", "resolved"},             # 处理中→暂缓 / 已处理→暂缓 都需原因
    "returned": {"pending"},                      # 待受理→已退回需原因
    "cancelled": {"pending", "open", "on_hold", "returned"},  # 撤销需原因
}

# 终态（不可再流转）
TERMINAL_STATES = {"archived", "cancelled"}

# ── Flow Log 动作类型 ─────────────────────────────────────────────
# 由 (from_state, to_state) 推导"这次流转是什么业务动作"。
# 集合完全来自上面的 TRANSITIONS 真实流转表（每条可达边恰好一票），
# 不在路由/前端另立动作清单。
TRANSITION_ACTIONS: dict[tuple[str | None, str], str] = {
    (None, "pending"): "create",            # 建单 / 草稿提交
    (None, "archived"): "instant_resolve",  # 即时办结咨询
    ("pending", "open"): "dispatch",        # 分派
    ("pending", "returned"): "return",      # 待受理退回
    ("pending", "cancelled"): "cancel",
    ("open", "resolved"): "resolve",        # 提交处理说明 / 手动办结
    ("open", "on_hold"): "hold",            # 暂缓
    ("open", "pending"): "return",          # 处理人打回
    ("open", "cancelled"): "cancel",
    ("on_hold", "resolved"): "resolve",
    ("on_hold", "open"): "resume",          # 恢复处理
    ("on_hold", "cancelled"): "cancel",
    ("resolved", "archived"): "archive",    # 归档
    ("resolved", "open"): "reopen",         # 退回重开
    ("resolved", "on_hold"): "reopen",      # 被 enforce_business_constraints 改写为 open，实际不可达
    ("returned", "pending"): "resubmit",    # 退回后重新提交
    ("returned", "cancelled"): "cancel",
}

# 全量动作类型（文档 / 测试断言用）。
# refine/transfer 不是状态流转边（from==to 的域动作，见 apply_refine /
# apply_transfer），故不在 TRANSITION_ACTIONS，单独并入。
ACTION_TYPES: set[str] = set(TRANSITION_ACTIONS.values()) | {"refine", "transfer"}


def action_for(
    from_state: str | None, to_state: str, override: str | None = None
) -> str | None:
    """推导 Flow Log 的 action_type；调用方可显式 override（未来特殊入口用）。"""
    if override is not None:
        return override
    return TRANSITION_ACTIONS.get((from_state, to_state))


# 动作的中文按钮文案（前端按 action 渲染，不再自配文案映射）
ACTION_LABELS: dict[str, str] = {
    "dispatch": "分派",
    "return": "退回",
    "cancel": "撤销",
    "resolve": "标记已处理",
    "hold": "暂缓处理",
    "resume": "恢复处理",
    "reopen": "退回重开",
    "resubmit": "重新提交",
    "archive": "归档",
    "refine": "分诊",     # 判断人细化分类一级（域动作，不改状态）
    "transfer": "转派",   # 多步链推进到下一部门（open→pending 的链语义）
}


# ── 文章（沟通记录）级状态/角色规则 ────────────────────────────
# 与状态机同源：articles 端点的服务端校验与详情页能力位（can_*）共用。
# 允许追加的工单状态：已处理之前（不包括已处理），以及退回后补充阶段
ADDITION_ALLOWED_STATES = {"pending", "open", "on_hold", "returned"}
# 允许追加的角色
ADDITION_ALLOWED_ROLES = {"admin", "agent"}
# 可提交处理说明的工单状态（处理人提交即流转到已处理）
REPLY_ALLOWED_STATES = {"open", "on_hold"}


def transition_precondition_error(ticket: Ticket, to_state: str) -> str | None:
    """状态无关的业务前置校验（领域闭环规则）。

    执行入口（apply_transition）与动作生成（compute_allowed_actions）共用，
    保证"按钮可见性"与"执行结果"永远一致。返回 None 表示无前置约束。
    """
    if to_state == "archived":
        if ticket.satisfaction == "dissatisfied":
            return "客户满意度为「不满意」，需退回重新处理并完成回访后才能归档"
        if ticket.customer_recognized is False:
            return "客户不认可处理结果，需退回重新处理并完成回访后才能归档"
        # 要求回访但尚未完成回访：先记录回访事实，再归档。
        # 两条规则互相独立——callback_required 是分类规则，is_callbacked 是回访事实。
        if ticket.callback_required and not ticket.is_callbacked:
            return "该工单要求回访，完成回访后才能归档"
    return None


async def compute_allowed_actions(
    db: AsyncSession, ticket: Ticket, user: User
) -> list[dict]:
    """生成工单在当前状态下"该用户可执行的状态动作"——后端唯一事实来源。

    完全由既有真实规则推导（不新增 if/else 业务规则）：
      候选目标 = TRANSITIONS[ticket.state]
      有效目标 = enforce_business_constraints（resolved→on_hold 改写为 open 并去重）
      动作     = action_for(from, effective)
      可执行   = transition_permission_error(...) is None（权限矩阵与执行入口同源）
      附加     = requires_reason（是否需填原因）/ requires_owner（分派须选处理人）
    终态返回 []。前端据此渲染按钮，点击后直接调用后端，不再自行判断。
    """
    actions: list[dict] = []
    from app.services.node_context import derive_node_type, node_action_error
    node_type, _, _ = await derive_node_type(db, ticket)
    seen: set[tuple[str, str]] = set()
    for to_state in TRANSITIONS.get(ticket.state, []):
        effective = enforce_business_constraints(ticket, to_state, log_rewrite=False)
        action = action_for(ticket.state, effective)
        if (
            action == "resolve"
            and ticket.dispatch_chain_steps
            and ticket.dispatch_step_index is not None
            and (
                ticket.dispatch_step_index + 1 < len(ticket.dispatch_chain_steps)
                or (
                    0 <= ticket.dispatch_step_index < len(ticket.dispatch_chain_steps)
                    and ticket.dispatch_chain_steps[ticket.dispatch_step_index].get("stage") == "phone_feedback"
                )
            )
        ):
            continue  # 中间节点/售后致电反馈须提交记录，不能直接整单办结
        if action is None or (action, effective) in seen:
            continue
        if await transition_permission_error(db, ticket, effective, user, enforce_node=False) is not None:
            continue
        if transition_precondition_error(ticket, effective) is not None:
            continue   # 业务前置未满足（如 dissatisfied 不可归档）→ 不出按钮
        seen.add((action, effective))
        actions.append({
            "action": action,
            "target_state": effective,
            "requires_reason": requires_reason(ticket.state, effective),
            "requires_owner": (ticket.state, effective) == ("pending", "open"),
            "label": ACTION_LABELS.get(action, action),
        })
    return [action for action in actions if node_action_error(node_type, action["action"]) is None]


def compute_article_actions(ticket: Ticket, user: User) -> dict[str, bool]:
    """详情页沟通记录能力位：与 articles 端点的服务端规则逐条对应。"""
    if ticket.state in TERMINAL_STATES:
        # 终态工单不接受任何沟通记录（与 create_article 的终态 422 对应）
        return {"can_reply": False, "can_addition": False}
    return {
        # 处理说明：仅当前处理人 + open/on_hold
        "can_reply": (
            ticket.owner_id is not None
            and user.id == ticket.owner_id
            and ticket.state in REPLY_ALLOWED_STATES
            and not (
                ticket.state == "on_hold"
                and ticket.dispatch_chain_steps
                and ticket.dispatch_step_index is not None
                and ticket.dispatch_step_index + 1 < len(ticket.dispatch_chain_steps)
            )
        ),
        # 追加：指定角色 + 已处理之前的状态
        "can_addition": (
            user.role in ADDITION_ALLOWED_ROLES
            and ticket.state in ADDITION_ALLOWED_STATES
        ),
    }


def validate_transition(from_state: str, to_state: str) -> None:
    """校验状态流转是否合法，非法则抛 StateTransitionError。"""
    # from_state 为 None 时走初始状态校验（建单）
    if from_state is None:
        validate_initial_state(to_state)
        return
    if from_state in TERMINAL_STATES:
        raise StateTransitionError(from_state, to_state)
    allowed = TRANSITIONS.get(from_state, [])
    if to_state not in allowed:
        raise StateTransitionError(from_state, to_state)


def requires_reason(from_state: str, to_state: str) -> bool:
    """该流转是否需要填写原因。"""
    return to_state in STATES_REQUIRE_REASON_FROM and from_state in STATES_REQUIRE_REASON_FROM[to_state]


def enforce_business_constraints(ticket: Ticket, target_state: str, log_rewrite: bool = True) -> str:
    """业务约束：已处理工单不允许直接退回到 on_hold（暂停位）。

    退回 resolved 工单的目标若为 on_hold，自动改写为 open。
    原因：on_hold 是暂停位，没人主动 unpause 就一直卡着；客服本意是
    "打回让处理人重做"，open 才是直接去处。

    改写对权限无影响（resolved→open 和 resolved→on_hold 的权限规则一致，
    都是 creator/agent 可操作）。
    """
    if ticket.state == "resolved" and target_state == "on_hold":
        if log_rewrite:  # 执行流转时记录一次；allowed_actions 推导时静默
            import logging
            ticket_id = getattr(ticket, "id", None)
            logging.getLogger(__name__).warning(
                f"[resolved→on_hold rewrite] ticket_id={ticket_id} "
                f"requested=on_hold → effective=open"
            )
        return "open"
    return target_state


def resolve_hold_until(hold_until: str | datetime | None) -> datetime:
    """校验并解析「预计恢复时间」。

    暂缓本身不涉及任何 SLA 语义：这个时间只表示预计什么时候恢复继续处理，
    不是 deadline。必填、格式必须合法、必须晚于当前时间。
    """
    if hold_until is None or (isinstance(hold_until, str) and not hold_until.strip()):
        raise HTTPException(422, detail="暂缓必须填写预计恢复时间")
    try:
        parsed = datetime.fromisoformat(str(hold_until).strip())
    except (TypeError, ValueError):
        raise HTTPException(
            422, detail="预计恢复时间格式不正确，应为 ISO 时间，如 2026-10-20T10:00") from None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    if parsed <= datetime.now(timezone.utc):
        raise HTTPException(422, detail="预计恢复时间必须晚于当前时间")
    return parsed


def snapshot_people(ticket: Ticket, body=None) -> dict:
    """写入 state_log 时的人员快照：进入新状态那一刻工单上的创建者/对接人/处理人。

    body 字段优先（代表正在应用的新值），未提供则回退到 ticket 当前值。
    - creator_id 永不变，直接取 ticket
    - dispatcher / owner：resubmit / 重新指派等场景下 body 会带新值
    - body 可能是 TicketCreate（无 owner_id 字段）或 TicketUpdate，用 getattr 兜底，
      避免直接属性访问抛 AttributeError
    """
    dispatcher_id = getattr(body, "dispatcher_id", None) if body is not None else None
    owner_id = getattr(body, "owner_id", None) if body is not None else None
    return {
        "creator_id_snapshot": ticket.creator_id,
        "dispatcher_id_snapshot": dispatcher_id if dispatcher_id is not None else ticket.dispatcher_id,
        "owner_id_snapshot": owner_id if owner_id is not None else ticket.owner_id,
    }


def snapshot_node(ticket: Ticket, *, state: str | None = None) -> dict:
    """Capture every field needed to put a ticket back at this workflow node."""
    return {
        "state": state or ticket.state,
        "category_id": ticket.category_id,
        "group_id": ticket.group_id,
        "skill_group_id": ticket.skill_group_id,
        "handler_skill_group_id": ticket.handler_skill_group_id,
        "owner_id": ticket.owner_id,
        "first_owner_id": ticket.first_owner_id,
        "dispatcher_id": ticket.dispatcher_id,
        "returned_to_user_id": ticket.returned_to_user_id,
        "dispatch_chain_steps": ticket.dispatch_chain_steps,
        "dispatch_step_index": ticket.dispatch_step_index,
        "resolved": False if state == "open" else ticket.resolved,
        "solved_at": None if state == "open" else (ticket.solved_at.isoformat() if ticket.solved_at else None),
    }


async def push_node(db: AsyncSession, ticket: Ticket, *, state: str | None = None) -> None:
    previous_log_id = (await db.execute(
        select(TicketStateLog.id).where(TicketStateLog.ticket_id == ticket.id)
        .order_by(TicketStateLog.id.desc()).limit(1)
    )).scalar_one_or_none()
    node = snapshot_node(ticket, state=state)
    node["previous_log_id"] = previous_log_id or 0
    ticket.return_checkpoints = [*(ticket.return_checkpoints or []), node]
    ticket.legacy_return_cursor_log_id = None


def restore_node(ticket: Ticket, node: dict) -> None:
    for field in (
        "state", "category_id", "group_id", "skill_group_id", "handler_skill_group_id",
        "owner_id", "first_owner_id", "dispatcher_id", "returned_to_user_id",
        "dispatch_chain_steps", "dispatch_step_index", "resolved",
    ):
        setattr(ticket, field, node[field])
    ticket.solved_at = datetime.fromisoformat(node["solved_at"]) if node["solved_at"] else None


async def _legacy_previous_node(db: AsyncSession, ticket: Ticket) -> tuple[dict | None, int | None]:
    """Infer one previous node from pre-checkpoint tickets; reject ambiguity."""
    query = select(TicketStateLog).where(TicketStateLog.ticket_id == ticket.id)
    if ticket.legacy_return_cursor_log_id == 0:
        return None, None
    if ticket.legacy_return_cursor_log_id is not None:
        query = query.where(TicketStateLog.id < ticket.legacy_return_cursor_log_id)
    logs = list((await db.execute(query.order_by(TicketStateLog.id.desc()).limit(50))).scalars().all())
    latest = next((log for log in logs if log.action_type not in ("return", "reopen")), None)
    if latest is None or latest.action_type in ("create", "resubmit"):
        return None, latest.id if latest else None
    node = snapshot_node(ticket)
    if latest.action_type == "transfer" and ticket.state == "pending":
        steps = ticket.dispatch_chain_steps or []
        index = ticket.dispatch_step_index
        if index is None or index < 1 or index >= len(steps):
            return None, latest.id
        from app.services.dispatch_chain import prescribe_dept
        prescribed = await prescribe_dept(db, steps[index - 1]["department_code"])
        if prescribed is None:
            return None, latest.id
        node.update(state="open", skill_group_id=prescribed["skill_group_id"],
                    handler_skill_group_id=prescribed["skill_group_id"],
                    owner_id=latest.operator_id, dispatcher_id=latest.dispatcher_id_snapshot,
                    dispatch_step_index=index - 1)
    elif latest.action_type == "refine" and ticket.state in ("pending", "open"):
        from app.models.category import TicketCategory
        from app.services.dispatch_chain import judging_department, prescribe_dept, resolve_chain
        parent_id = (await db.execute(
            select(TicketCategory.parent_id).where(TicketCategory.id == ticket.category_id)
        )).scalar_one_or_none()
        if parent_id is None:
            return None, latest.id
        department = await judging_department(db, parent_id)
        prescribed = await prescribe_dept(db, department) if department else None
        previous_log = next((log for log in logs if log.id < latest.id), None)
        previous_chain = await resolve_chain(db, parent_id)
        if previous_log is None or prescribed is None:
            return None, latest.id
        node.update(category_id=parent_id, skill_group_id=prescribed["skill_group_id"],
                    handler_skill_group_id=prescribed["skill_group_id"],
                    owner_id=previous_log.owner_id_snapshot,
                    dispatcher_id=previous_log.dispatcher_id_snapshot,
                    dispatch_chain_steps=previous_chain["steps"] if previous_chain else None,
                    dispatch_step_index=0)
    elif latest.action_type == "dispatch" and ticket.state == "open":
        node.update(state="pending", owner_id=None)
    elif latest.action_type == "resolve" and ticket.state == "resolved":
        node.update(state="open", resolved=False, solved_at=None)
    elif latest.action_type == "hold" and ticket.state == "on_hold":
        node.update(state="open")
    else:
        return None, latest.id
    return node, latest.id


async def _legacy_is_initial(db: AsyncSession, ticket: Ticket, cursor: int) -> bool:
    action = (await db.execute(
        select(TicketStateLog.action_type).where(TicketStateLog.id == cursor,
                                                 TicketStateLog.ticket_id == ticket.id)
    )).scalar_one_or_none()
    return action in ("create", "resubmit")


async def apply_return(db: AsyncSession, ticket: Ticket, *, operator: User, reason: str) -> TicketStateLog:
    """Return to the prior workflow node, restoring its category and assignee."""
    if not reason.strip():
        raise HTTPException(400, detail="退回原因不能为空")
    permission_target = {
        "pending": "returned", "open": "pending", "on_hold": "open", "resolved": "open",
    }.get(ticket.state)
    if permission_target is None:
        raise HTTPException(422, detail="当前状态不能退回")
    error = await transition_permission_error(db, ticket, permission_target, operator)
    if error is not None:
        raise ForbiddenError(error)

    old_state = ticket.state
    checkpoints = ticket.return_checkpoints or []
    if checkpoints:
        node = checkpoints[-1]
        ticket.return_checkpoints = checkpoints[:-1]
        restore_node(ticket, node)
        if not ticket.return_checkpoints:
            ticket.legacy_return_cursor_log_id = node.get("previous_log_id", 0) + 1
    else:
        node, cursor = await _legacy_previous_node(db, ticket)
        if node is not None:
            restore_node(ticket, node)
            ticket.legacy_return_cursor_log_id = cursor
        elif ticket.state == "pending" and cursor is not None and await _legacy_is_initial(db, ticket, cursor):
            # Initial node: the creator is the only previous participant.
            ticket.state = "returned"
            ticket.owner_id = ticket.creator_id
            ticket.returned_to_user_id = ticket.creator_id
            ticket.legacy_return_cursor_log_id = cursor
        else:
            raise HTTPException(422, detail="历史工单缺少可确认的上一节点，无法安全退回")
    if old_state == "resolved":
        ticket.satisfaction = None
        ticket.customer_recognized = None
        ticket.customer_satisfaction_score = None
    db.expire(ticket, ["category", "skill_group", "handler_skill_group", "owner", "dispatcher", "returned_to_user", "first_owner", "group"])
    ticket.has_returned = True
    now = datetime.now(timezone.utc)
    last = (await db.execute(
        select(TicketStateLog).where(TicketStateLog.ticket_id == ticket.id)
        .order_by(TicketStateLog.created_at.desc(), TicketStateLog.id.desc()).limit(1)
    )).scalar_one_or_none()
    log = TicketStateLog(
        ticket_id=ticket.id, from_state=old_state, to_state=ticket.state,
        operator_id=operator.id, reason=reason,
        duration_minutes=int((now - last.created_at).total_seconds() / 60) if last else None,
        action_type="reopen" if old_state == "resolved" else "return",
        **snapshot_people(ticket),
    )
    db.add(log)
    await db.flush()
    return log


async def is_dispatcher(db: AsyncSession, user_id: int, skill_group_id: int | None) -> bool:
    """检查用户是否为某对接部门的部门对接人。"""
    if not skill_group_id:
        return False
    result = await db.execute(
        select(UserSkillGroup).where(
            UserSkillGroup.user_id == user_id,
            UserSkillGroup.skill_group_id == skill_group_id,
            UserSkillGroup.is_dispatcher == True,
        )
    )
    return result.scalar_one_or_none() is not None


async def transition_permission_error(
    db: AsyncSession, ticket: Ticket, to_state: str, user: User,
    *, allow_phone_feedback_reply: bool = False, enforce_node: bool = True,
    allow_sales_intake: bool = False, allow_sales_completion: bool = False,
    allow_reconciliation_handoff: bool = False,
) -> str | None:
    """身份/角色层面是否允许该状态变更：允许返回 None，否则返回错误文案。

    与 check_transition_permission 共用同一套矩阵（只定义一次）；
    allowed_actions 的生成也调用它，路由/前端不再另写 if/else。
    分派场景"必须指定处理人"属于输入要求，由 check_transition_permission 判定。
    """
    if enforce_node:
        from app.services.node_context import derive_node_type, node_action_error
        node_type, _, _ = await derive_node_type(db, ticket)
        node_error = node_action_error(node_type, action_for(ticket.state, to_state) or "")
        if node_error is not None and not (
            (node_type == "phone_feedback" and to_state == "resolved" and allow_phone_feedback_reply)
            or (node_type == "sales_opportunity" and to_state == "resolved" and allow_sales_completion)
            or (node_type == "sales_opportunity" and to_state == "open" and allow_sales_intake)
        ):
            return node_error
    if user.role == "admin":
        return None  # admin 全权限

    from_state = ticket.state

    # 分派：部门对接人
    if (from_state, to_state) == ("pending", "open"):
        if allow_reconciliation_handoff and ticket.category_id == 2204 and ticket.skill_group_id is not None:
            return None
        if allow_sales_intake and (ticket.is_opportunity or ticket.category_id == 2204) and ticket.creator_id == user.id:
            return None
        steps = ticket.dispatch_chain_steps or []
        step_index = ticket.dispatch_step_index
        if (
            step_index is not None and step_index < len(steps)
            and steps[step_index].get("stage") == "phone_feedback"
        ):
            if ticket.dispatcher_id != user.id or ticket.skill_group_id is None:
                return "仅当前售后致电反馈对接人可分派工单"
            member = await db.scalar(select(UserSkillGroup.user_id).where(
                UserSkillGroup.user_id == user.id,
                UserSkillGroup.skill_group_id == ticket.skill_group_id,
            ))
            if member is not None:
                return None
            return "售后致电反馈对接人不属于当前责任部门"
        if not await is_dispatcher(db, user.id, ticket.skill_group_id):
            return "只有该部门的对接人可分派工单"
        return None

    # 处理人操作：已处理 / 暂缓 / 确认 / 退回上一状态
    if (from_state, to_state) in [
        ("open", "resolved"), ("open", "on_hold"), ("on_hold", "resolved"),
        ("open", "pending"), ("on_hold", "open"),
    ]:
        if ticket.owner_id != user.id:
            return "只有当前处理人可执行此操作"
        return None

    # 已处理状态退回：业务上已回到客服侧，由创建者或客服团队退回
    if (from_state, to_state) in [("resolved", "open"), ("resolved", "on_hold")]:
        if ticket.creator_id == user.id:
            return None
        if user.role == "agent":
            return None
        return "只有创建者或客服团队可退回已处理工单"

    # 撤销：仅创建者（发起人）
    if to_state == "cancelled" and from_state in ("pending", "open", "on_hold", "returned"):
        if ticket.creator_id == user.id:
            return None
        return "只有工单发起人可撤销工单"

    # 客服团队操作：归档
    if (from_state, to_state) in [("resolved", "archived")]:
        if allow_sales_completion and ticket.is_opportunity and ticket.owner_id == user.id:
            return None
        if user.role != "agent":
            return "只有客服团队可执行归档操作"
        return None

    # 待受理退回：部门对接人 → 已退回，处理人给创建者
    if (from_state, to_state) == ("pending", "returned"):
        if await is_dispatcher(db, user.id, ticket.skill_group_id):
            return None
        return "只有部门对接人可退回待受理工单"

    # 已退回工单：创建者可重新提交或撤销
    if from_state == "returned" and to_state in ("pending", "cancelled"):
        if ticket.creator_id == user.id:
            return None
        return "只有创建者可处理已退回工单"

    return "无权执行此状态变更"


async def check_transition_permission(
    db: AsyncSession, ticket: Ticket, to_state: str, user: User, owner_id: int | None = None,
    *, allow_phone_feedback_reply: bool = False,
    allow_sales_intake: bool = False, allow_sales_completion: bool = False,
    allow_reconciliation_handoff: bool = False,
) -> None:
    """校验当前用户是否有权执行该状态变更（非法则抛 ForbiddenError / 422）。

    权限矩阵（唯一定义处 → transition_permission_error）：
      pending→open（分派）: 部门对接人 / admin
      open→resolved / on_hold, on_hold→resolved: 处理人（owner）/ admin
      pending/open/on_hold/resolved→cancelled（撤销）: 创建者 / 部门对接人 / admin
      resolved→archived（归档）: 客服团队(agent) / admin
      退回：
        pending→returned: 部门对接人 / admin
        open→pending: 处理人（owner）/ admin
        on_hold→open: 处理人（owner）/ admin
        resolved→open/on_hold: 处理人（owner）/ admin
      returned→pending/cancelled: 创建者 / admin
    分派的输入要求：非 admin 分派必须指定处理人（422）。
    分派还需处理人属于工单当前责任部门（skill_group_id）——对齐
    routing.validate_rule_payload 的同名约束，避免跨部门错配（admin 同样受约束）。
    """
    error = await transition_permission_error(
        db, ticket, to_state, user,
        allow_phone_feedback_reply=allow_phone_feedback_reply,
        allow_sales_intake=allow_sales_intake,
        allow_sales_completion=allow_sales_completion,
        allow_reconciliation_handoff=allow_reconciliation_handoff,
    )
    if error is not None:
        raise ForbiddenError(error)
    if (ticket.state, to_state) == ("pending", "open"):
        if user.role != "admin" and not owner_id:
            raise HTTPException(422, detail="分派时必须指定处理人")
        target_id = owner_id or ticket.owner_id
        if target_id and ticket.skill_group_id:
            await _assert_user_in_department(
                db, target_id, ticket.skill_group_id, "处理人"
            )


async def _assert_user_in_department(
    db: AsyncSession, user_id: int, skill_group_id: int, role_label: str
) -> None:
    """人员必须属于指定部门，否则 422。

    前端选人控件已按部门过滤，这里是后端兜底：admin 或直接调接口都能绕过前端，
    实测就出现过工单责任部门=经营管理部、处理人=网运部成员的错配。
    """
    link = await db.execute(
        select(UserSkillGroup).where(
            UserSkillGroup.user_id == user_id,
            UserSkillGroup.skill_group_id == skill_group_id,
        )
    )
    if link.scalar_one_or_none() is None:
        dept = await db.execute(
            select(SkillGroup.name).where(SkillGroup.id == skill_group_id)
        )
        raise HTTPException(
            422,
            detail=(
                f"{role_label}不属于工单当前责任部门"
                f"「{dept.scalar_one_or_none() or skill_group_id}」"
            ),
        )


async def apply_initial_state(
    db: AsyncSession,
    ticket: Ticket,
    *,
    to_state: str,
    operator: User,
    reason: str | None = None,
    body=None,
    action_type: str | None = None,
) -> TicketStateLog:
    """建单 / 草稿提交 / 即时办结的初始状态落库：None → pending / archived。

    与 apply_transition 共享同一套公共实现：
      - 初始态合法性：validate_initial_state（仅 pending / archived）
      - 终态副作用：closed_at / closed_duration_minutes（即时办结 → archived）
      - Flow Log：from_state=None、停留时长为 None、人员快照、action_type
    调用方负责业务数据字段（number / SLA 截止时间 / resolution / 回访标志等）
    与显式提交；草稿（is_draft=True）不写初始日志，由调用方跳过本方法。
    """
    validate_initial_state(to_state)
    now = datetime.now(timezone.utc)

    if to_state in TERMINAL_STATES:
        ticket.closed_at = now
        if ticket.created_at:
            ticket.closed_duration_minutes = int((now - ticket.created_at).total_seconds() / 60)

    ticket.state = to_state
    log = TicketStateLog(
        ticket_id=ticket.id, from_state=None, to_state=to_state,
        operator_id=operator.id, reason=reason, duration_minutes=None,
        action_type=action_for(None, to_state, action_type),
        **snapshot_people(ticket, body),
    )
    db.add(log)
    await db.flush()
    return log


# ── 分诊（refine_category）：判断人细化分类一级 → 按新链重新派单 ──
# 设计：docs/ticket_dispatch_design.md §2「分诊动作的语义」。
# 域动作而非状态流转：from==to 自环 Flow Log，action_type=refine。
# 权限与执行仍收口在本模块（与 apply_transition 同一入口纪律）。


async def refine_capability(
    db: AsyncSession, ticket: Ticket, user: User
) -> dict:
    """详情页分诊能力位：can_refine + 可细化到的下级分类 + 拒绝原因。

    规则（设计 §2）：
      - 仅 pending/open 可分诊（on_hold 先恢复；终态/已处理不可回溯）；
      - 判断人 = 当前分类链的第 1 步部门的生效成员（admin 越权豁免）；
      - 当前分类必须有下级（已是判断末级则无可细化对象）。
    """
    from app.services.dispatch_chain import (
        category_children,
        is_dept_member,
        judging_department,
        resolve_chain,
    )

    out: dict = {
        "can_refine": False,
        "refine_options": [],
        "refine_denied_reason": None,
    }
    if ticket.state not in ("pending", "open"):
        out["refine_denied_reason"] = "仅待受理/处理中的工单可分诊"
        return out
    if ticket.category_id is None:
        out["refine_denied_reason"] = "工单未选择分类，无法分诊"
        return out
    if ticket.category_id == 2301:
        if ticket.state != "open" or ticket.owner_id is None:
            out["refine_denied_reason"] = "请先由售后负责人指派售后人员"
            return out
        if ticket.owner_id != user.id and user.role != "admin":
            out["refine_denied_reason"] = "仅被指派的售后人员可进行问题判断"
            return out
    children = await category_children(db, ticket.category_id)
    if not children:
        out["refine_denied_reason"] = "该分类已是判断末级，无需分诊"
        return out
    from app.services.node_context import derive_node_type
    node_type, _, _ = await derive_node_type(db, ticket)
    if node_type != "triage":
        out["refine_denied_reason"] = "当前职责节点不是问题分诊"
        return out
    if user.role != "admin":
        dept = await judging_department(db, ticket.category_id)
        if dept is None:
            out["refine_denied_reason"] = "该分类未配置判断链，无法分诊"
            return out
        if not await is_dept_member(db, user.id, dept):
            out["refine_denied_reason"] = f"仅「{dept}」的判断人可分诊"
            return out
    out["can_refine"] = True
    # 每个可细化项带上"细化为它之后会落位到哪个部门"，供前端二次确认展示
    # （落位规则与 apply_refine 一致：新链首步==当前判断部门则跳过，否则落位新链首）
    current_judging = await judging_department(db, ticket.category_id)
    options: list[dict] = []
    for c in children:
        next_dept: str | None = None
        chain = await resolve_chain(db, c.id)
        if chain and chain["steps"]:
            head = chain["steps"][0]["department_code"]
            if head != current_judging:
                next_dept = head
        options.append(
            {"id": c.id, "name": c.name, "level": c.level, "next_department": next_dept}
        )
    out["refine_options"] = options
    return out


async def refine_permission_error(
    db: AsyncSession, ticket: Ticket, user: User
) -> str | None:
    """分诊权限/前置：允许返回 None，否则返回错误文案。"""
    cap = await refine_capability(db, ticket, user)
    if cap["can_refine"]:
        return None
    return cap["refine_denied_reason"] or "无权执行分诊"


async def apply_refine(
    db: AsyncSession,
    ticket: Ticket,
    *,
    new_category_id: int,
    operator: User,
) -> TicketStateLog:
    """分诊执行入口：分类细化一级 → 按新分类链重算快照并落位部门/处理人。

    收口顺序（与 apply_transition 同纪律）：
      1. 权限/前置（refine_permission_error：状态、判断人、有下级）
      2. 目标校验：必须是当前分类的直下级且启用（不能跳级、不能凭空改）
      3. 链重算（resolve_chain 按新分类查配置）+ 接续规则：
         - 新链首步 == 当前判断部门 → 跳过该步（无下一步则落位不变，
           即"判断方=处理方"的硬件故障场景）
         - 否则 → 落位到新链首步部门
      4. 人员处方：skill_group/dispatcher 切到目标部门；open 状态下
         owner 一并切换（"当前节点的处理人分给谁就是谁"）
      5. Flow Log：from==to 自环，action_type=refine，reason 记录分类变化

    不负责 commit——由调用方按请求边界提交。
    """
    from app.models.category import TicketCategory
    from app.services.dispatch_chain import (
        judging_department,
        prescribe_dept,
        resolve_chain,
    )

    err = await refine_permission_error(db, ticket, operator)
    if err is not None:
        raise ForbiddenError(err)

    target = (
        await db.execute(
            select(TicketCategory).where(TicketCategory.id == new_category_id)
        )
    ).scalar_one_or_none()
    if target is None or not target.is_active:
        raise HTTPException(404, detail=f"目标分类不存在或已停用: {new_category_id}")
    if target.parent_id != ticket.category_id:
        raise HTTPException(
            400, detail="分诊只能细化到当前分类的直下级（不能跳级或改往其他分支）"
        )

    old_category = ticket.category
    old_name = old_category.name if old_category else str(ticket.category_id)
    new_name = target.name

    judging_dept = await judging_department(db, ticket.category_id)
    new_chain = await resolve_chain(db, target.id)
    steps = new_chain["steps"] if new_chain else []

    # 接续规则（设计 §4）：新链首步 == 判断部门 → 跳过；无下一步 → 落位不变
    step_index = 0
    move_dept: str | None = None
    if steps:
        if judging_dept is not None and steps[0]["department_code"] == judging_dept:
            if len(steps) > 1:
                step_index = 1
                move_dept = steps[1]["department_code"]
            else:
                step_index = 0
                move_dept = None  # 判断方=处理方：部门/处理人保持
        else:
            step_index = 0
            move_dept = steps[0]["department_code"]

    await push_node(db, ticket)
    ticket.category_id = target.id
    # 分诊细化会改变分类：是否需要回访随新分类重算，仍由分类规则唯一决定。
    ticket.callback_required = await resolve_callback_required(db, target.id)
    ticket.dispatch_chain_steps = steps or ticket.dispatch_chain_steps
    ticket.dispatch_step_index = step_index if steps else ticket.dispatch_step_index

    if move_dept is not None:
        rx = await prescribe_dept(db, move_dept)
        if rx is not None:
            ticket.skill_group_id = rx["skill_group_id"]
            ticket.handler_skill_group_id = rx["skill_group_id"]
            if rx["dispatcher_id"] is not None:
                ticket.dispatcher_id = rx["dispatcher_id"]
            # open 态：直接把处理人切到目标部门处方（链规定，不是自由选择）
            if ticket.state == "open" and rx["owner_id"] is not None:
                ticket.owner_id = rx["owner_id"]

    log = TicketStateLog(
        ticket_id=ticket.id,
        from_state=ticket.state,
        to_state=ticket.state,
        operator_id=operator.id,
        reason=f"分诊：{old_name} → {new_name}",
        duration_minutes=None,
        action_type="refine",
        **snapshot_people(ticket),
    )
    db.add(log)
    await db.flush()
    return log


async def transfer_permission_error(
    db: AsyncSession, ticket: Ticket, user: User
) -> str | None:
    """转派权限/前置：允许返回 None，否则返回错误文案。

    转派 = 多步链本步完成、推进到链的下一部门（设计 §4）：
      - 仅处理中（open）可转派——pending 等对接人分派、终态不可回溯；
      - 工单必须走链且还有下一步（链末步/无链工单无处可转）；
      - 触发人 = 当前处理人自己（与 open→pending 退回同一身份口径）/ admin。
    """
    if ticket.state != "open":
        return "仅处理中的工单可转派"
    steps = ticket.dispatch_chain_steps
    idx = ticket.dispatch_step_index
    if not steps or idx is None:
        return "该工单未走分派链，无法转派"
    if idx + 1 >= len(steps):
        return "当前已是链上最后一步，无需转派"
    if user.role != "admin" and ticket.owner_id != user.id:
        return "只有当前处理人可转派"
    return None


async def apply_transfer(
    db: AsyncSession,
    ticket: Ticket,
    *,
    operator: User,
    reason: str | None = None,
) -> TicketStateLog:
    """转派执行入口：链快照推进一步 → 工单落到下一部门的待受理。

    收口顺序（与 apply_refine / apply_transition 同纪律）：
      1. 前置（transfer_permission_error：状态、链上有下一步、处理人身份）
      2. 下一步部门处方（部门代称 → skill_group/dispatcher）
      3. 步骤推进 + 部门落位（先改人员，Flow Log 快照记新部门）
      4. 状态推进复用 apply_transition 唯一入口（open→pending：清 owner、
         记停留时长、原因校验），action_type 覆盖为 "transfer"——
         与"处理人打回"同一条边但语义是链前进
      5. 保留历史退回标记：转派是前进，不新增退回历史

    不负责 commit——由调用方按请求边界提交。
    """
    from app.services.dispatch_chain import prescribe_dept

    err = await transfer_permission_error(db, ticket, operator)
    if err is not None:
        raise ForbiddenError(err)

    steps = ticket.dispatch_chain_steps or []
    next_index = (ticket.dispatch_step_index or 0) + 1
    next_dept = steps[next_index]["department_code"]
    rx = await prescribe_dept(db, next_dept)
    if rx is None:
        raise HTTPException(422, detail=f"链上下一步部门不存在：{next_dept}")

    # 步骤推进 + 部门落位（owner 由下面 open→pending 的副作用清空，
    # 下一部门对接人在 pending→open 分派时指定处理人）
    await push_node(db, ticket)
    ticket.dispatch_step_index = next_index
    ticket.skill_group_id = rx["skill_group_id"]
    ticket.handler_skill_group_id = rx["skill_group_id"]
    feedback_judger_id = None
    if steps[next_index].get("stage") == "phone_feedback":
        # 业务保障的问题判断由售后人员完成。回到售后致电反馈时，
        # 由该判断人指派反馈人，而不是重新取售后组的默认对接人。
        feedback_judger_id = await db.scalar(
            select(TicketStateLog.operator_id)
            .join(UserSkillGroup, UserSkillGroup.user_id == TicketStateLog.operator_id)
            .where(
                TicketStateLog.ticket_id == ticket.id,
                TicketStateLog.action_type == "refine",
                TicketStateLog.reason.like("分诊：业务保障 → %"),
                UserSkillGroup.skill_group_id == rx["skill_group_id"],
            )
            .order_by(TicketStateLog.id)
            .limit(1)
        )
    next_dispatcher_id = feedback_judger_id or rx["dispatcher_id"]
    if next_dispatcher_id is not None:
        ticket.dispatcher_id = next_dispatcher_id
    # 转派本步不设处理人（open→pending 会清空 owner），错配只可能出现在下一步
    # 分派——那里已校验处理人属于当时的 skill_group_id。此处再断言一次处方给出
    # 的对接人属于新落位部门，防 prescribe_dept 返回异常数据导致跨部门落位。
    if next_dispatcher_id is not None:
        await _assert_user_in_department(
            db, next_dispatcher_id, rx["skill_group_id"], "链上对接人"
        )

    log = await apply_transition(
        db,
        ticket,
        to_state="pending",
        operator=operator,
        reason=reason or ("本步完成，流转至售后致电反馈" if steps[next_index].get("stage") == "phone_feedback" else f"本步完成，转派「{next_dept}」"),
        action_type="transfer",
    )
    await db.flush()
    return log


async def apply_transition(
    db: AsyncSession,
    ticket: Ticket,
    *,
    to_state: str,
    operator: User,
    reason: str | None = None,
    owner_id: int | None = None,
    dispatcher_id: int | None = None,
    hold_until: str | None = None,
    action_type: str | None = None,
    allow_intermediate_transfer: bool = False,
    allow_sales_intake: bool = False,
    allow_sales_completion: bool = False,
    allow_reconciliation_handoff: bool = False,
) -> TicketStateLog | None:
    """单条工单状态流转的唯一执行入口。

    收口顺序（与原 update_ticket 单条 PATCH 语义一致）：
      1. 业务约束改写（resolved→on_hold → open）
      2. validate_transition（合法性）
      3. check_transition_permission（角色/身份权限 + 分派须指定处理人）
      4. requires_reason（退回/暂缓/撤销必须填原因）
      5. transition_precondition_error（业务前置校验：如 dissatisfied 不可归档）
      6. 状态副作用（first_owner/solved_at/resolved/SLA breach/owner 清理/
         returned_to_user/closed_at/closed_duration_minutes/hold_until）
      7. 应用调用方给出的人员字段（显式值优先于副作用）
      8. has_returned 同步 + 写 Flow Log（含上一状态停留时长与人员快照、action_type）

    暂缓（open→on_hold）：reason 必填、hold_until 必填且必须晚于当前时间；
    恢复（on_hold→open）：reason 必填，路由字段全部保持，仅清空 hold_until /
    hold_reminded_at。两者都不涉及任何 SLA 计时语义。

    返回写入的 TicketStateLog；to_state 与当前状态相同（no-op）时返回 None。
    不负责 commit——由调用方按各自的请求边界提交。
    """
    # 中间节点只能通过处理说明完成本步并进入下一部门；
    # 直接 PATCH 状态不能绕过办理记录。
    steps = ticket.dispatch_chain_steps or []
    from app.services.node_context import derive_node_type, node_action_error
    node_type, _, _ = await derive_node_type(db, ticket)
    action_error = node_action_error(node_type, action_for(ticket.state, to_state, action_type) or "")
    if action_error is not None and action_type != "transfer" and not (
        (node_type == "phone_feedback" and to_state == "resolved" and allow_intermediate_transfer)
        or (node_type == "sales_opportunity" and to_state == "resolved" and allow_sales_completion)
        or (node_type == "sales_opportunity" and to_state == "open" and allow_sales_intake)
    ):
        if action_for(ticket.state, to_state, action_type) == "dispatch":
            raise ForbiddenError(action_error)
        raise HTTPException(422, detail=action_error)
    if ticket.state == "on_hold" and to_state == "on_hold":
        # 不接受「直接在暂缓中改预计恢复时间」：同状态会被当成 no-op 静默成功，
        # 客户端会误以为改成功了。调整时间必须先恢复处理再重新暂缓。
        raise HTTPException(
            422, detail="已在暂缓中；如需调整预计恢复时间，请先恢复处理再重新暂缓")
    is_phone_feedback = (
        ticket.dispatch_step_index is not None
        and 0 <= ticket.dispatch_step_index < len(steps)
        and steps[ticket.dispatch_step_index].get("stage") == "phone_feedback"
    )
    if is_phone_feedback and to_state == "resolved" and not allow_intermediate_transfer:
        raise HTTPException(422, detail="请提交售后致电反馈记录后完成当前节点")
    if (
        ticket.state == "on_hold"
        and to_state == "resolved"
        and ticket.dispatch_step_index is not None
        and ticket.dispatch_step_index + 1 < len(steps)
    ):
        raise HTTPException(422, detail="当前节点须先恢复处理，再提交并流转至下一部门")
    if (
        ticket.state == "open"
        and to_state == "resolved"
        and ticket.dispatch_step_index is not None
        and ticket.dispatch_step_index + 1 < len(steps)
    ):
        if not allow_intermediate_transfer:
            raise HTTPException(422, detail="请提交处理说明，完成当前节点并流转至下一部门")
        return await apply_transfer(db, ticket, operator=operator, reason=reason)

    # 1. 业务约束
    to_state = enforce_business_constraints(ticket, to_state)
    if to_state == ticket.state:
        return None

    # 2. 合法性
    validate_transition(ticket.state, to_state)

    # 3. 权限
    await check_transition_permission(
        db, ticket, to_state, operator, owner_id,
        allow_phone_feedback_reply=allow_intermediate_transfer,
        allow_sales_intake=allow_sales_intake,
        allow_sales_completion=allow_sales_completion,
        allow_reconciliation_handoff=allow_reconciliation_handoff,
    )

    # 4. 原因必填
    if requires_reason(ticket.state, to_state) and not (reason or "").strip():
        raise HTTPException(
            400,
            detail=(
                f"从「{STATE_LABELS.get(ticket.state, ticket.state)}」"
                f"变更为「{STATE_LABELS.get(to_state, to_state)}」需要填写原因"
            ),
        )

    # 暂缓：预计恢复时间必填且合法（与 SLA 无关，仅用于到期提醒）
    hold_until_at = resolve_hold_until(hold_until) if to_state == "on_hold" else None

    # 5. 业务前置校验（客户闭环规则，与 allowed_actions 同一份判定）
    precondition = transition_precondition_error(ticket, to_state)
    if precondition is not None:
        raise HTTPException(422, detail=precondition)

    action = action_for(ticket.state, to_state, action_type)
    if action in RETURN_ACTIONS:
        return await apply_return(db, ticket, operator=operator, reason=reason or "")
    if action == "dispatch":
        await push_node(db, ticket)
    elif action == "resolve":
        await push_node(db, ticket, state="open" if ticket.state == "on_hold" else None)

    old_state = ticket.state
    now = datetime.now(timezone.utc)

    # 6. 状态副作用
    if to_state == "open":
        if old_state == "pending":
            # 分派处理人：pending→open 时由对接人指定 owner_id；
            # first_owner 记录被指派的首任处理人，无人可退时记操作人
            ticket.first_owner_id = (owner_id if owner_id is not None else ticket.owner_id) or operator.id
        elif old_state == "returned":
            # 已退回工单重新提交：保持无处理人，等待再次分派
            ticket.returned_to_user_id = None
        elif old_state == "resolved":
            # 退回重开：上一轮回访结果随工单失效，满意度清零等待再次回访
            # （callback_details 保留为历史记录；不清空则不满意会永久隐藏
            #  归档动作，重开后再也无法完成闭环）
            ticket.satisfaction = None
            ticket.customer_recognized = None
            ticket.customer_satisfaction_score = None
        elif old_state == "on_hold":
            # 恢复处理 = 回到原节点继续，不重新路由（上面未触碰任何路由字段）。
            # 预计恢复时间与提醒标记一并清空，下一轮暂缓重新计时、可再次提醒一次。
            ticket.hold_until = None
            ticket.hold_reminded_at = None
    elif to_state == "pending":
        # open→pending 退回 或 returned→pending 重新提交：待受理无处理人
        if old_state in ("open", "returned"):
            ticket.owner_id = None
            ticket.returned_to_user_id = None
    elif to_state == "on_hold":
        # on_hold←open（暂缓）/ on_hold←resolved（退回）：处理人保持不变
        # TODO(sla-policy): SLA 策略未定，暂不在进/出 on_hold 时调整 solution_deadline
        pass
    elif to_state == "resolved":
        ticket.solved_at = now
        ticket.resolved = True
        if ticket.solution_deadline and now > ticket.solution_deadline:
            ticket.sla_solution_breached = True
    elif to_state == "returned":
        # 仅 pending→returned：分配给创建工单的客服人员
        if old_state == "pending":
            ticket.returned_to_user_id = ticket.creator_id
            ticket.owner_id = ticket.creator_id
    elif to_state in ("archived", "cancelled"):
        # 终态：记录结案时间
        ticket.closed_at = now
        if ticket.created_at:
            ticket.closed_duration_minutes = int((now - ticket.created_at).total_seconds() / 60)

    # 7. 显式人员字段（覆盖副作用，与原 PATCH 语义一致）
    if owner_id is not None:
        ticket.owner_id = owner_id
    if dispatcher_id is not None:
        ticket.dispatcher_id = dispatcher_id

    # 暂缓：落库预计恢复时间（已在上面校验）
    if hold_until_at is not None:
        ticket.hold_until = hold_until_at

    # 一旦发生退回或退回重开，就永久保留历史标记；转派等后续动作不清除。
    action = action_for(old_state, to_state, action_type)
    ticket.has_returned = ticket.has_returned or action in RETURN_ACTIONS
    ticket.state = to_state

    # 上一状态停留时长
    last_log = await db.execute(
        select(TicketStateLog)
        .where(TicketStateLog.ticket_id == ticket.id)
        .order_by(TicketStateLog.created_at.desc()).limit(1)
    )
    last = last_log.scalar_one_or_none()
    duration = int((now - last.created_at).total_seconds() / 60) if last else None

    # Flow Log（快照取的是 ticket 已应用新值后的人员；action_type 由流转边推导）
    log = TicketStateLog(
        ticket_id=ticket.id, from_state=old_state, to_state=to_state,
        operator_id=operator.id, reason=reason, duration_minutes=duration,
        action_type=action,
        **snapshot_people(ticket),
    )
    db.add(log)
    await db.flush()
    return log
