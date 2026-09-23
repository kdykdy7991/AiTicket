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
from app.models.group import UserSkillGroup
from app.models.ticket import Ticket, TicketStateLog
from app.models.user import User

# 状态的中文展示名（错误信息 / 导出 / allowed_actions label 共用）
STATE_LABELS: dict[str, str] = {
    "pending": "待受理", "open": "处理中", "resolved": "已处理",
    "on_hold": "暂缓处理", "returned": "退回",
    "archived": "已归档", "cancelled": "已撤销",
}

# 哪些状态转换算"退回"动作，写完 state_log 后用来同步 has_returned
# - (pending, returned): 客户/客服 退回给创建人
# - (open, pending):     处理人退回给团队负责人（重新分派）
RETURN_TRANSITIONS: set[tuple[str, str]] = {
    ("pending", "returned"),
    ("open", "pending"),
}

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


def enforce_business_constraints(ticket: Ticket, target_state: str) -> str:
    """业务约束：已处理工单不允许直接退回到 on_hold（暂停位）。

    退回 resolved 工单的目标若为 on_hold，自动改写为 open。
    原因：on_hold 是暂停位，没人主动 unpause 就一直卡着；客服本意是
    "打回让处理人重做"，open 才是直接去处。

    改写对权限无影响（resolved→open 和 resolved→on_hold 的权限规则一致，
    都是 creator/agent 可操作）。
    """
    if ticket.state == "resolved" and target_state == "on_hold":
        import logging
        ticket_id = getattr(ticket, "id", None)
        logging.getLogger(__name__).warning(
            f"[resolved→on_hold rewrite] ticket_id={ticket_id} "
            f"requested=on_hold → effective=open"
        )
        return "open"
    return target_state


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


async def check_transition_permission(
    db: AsyncSession, ticket: Ticket, to_state: str, user: User, owner_id: int | None = None
) -> None:
    """校验当前用户是否有权执行该状态变更。

    权限矩阵：
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
    """
    if user.role == "admin":
        return  # admin 全权限

    from_state = ticket.state

    # 分派：部门对接人
    if from_state == "pending" and to_state == "open":
        if not await is_dispatcher(db, user.id, ticket.skill_group_id):
            raise ForbiddenError("只有该部门的对接人可分派工单")
        # 分派时必须指定处理人
        if not owner_id:
            raise HTTPException(422, detail="分派时必须指定处理人")
        return

    # 处理人操作：已处理 / 暂缓 / 确认 / 退回上一状态
    if (from_state, to_state) in [
        ("open", "resolved"), ("open", "on_hold"), ("on_hold", "resolved"),
        ("open", "pending"), ("on_hold", "open"),
    ]:
        if ticket.owner_id != user.id:
            raise ForbiddenError("只有当前处理人可执行此操作")
        return

    # 已处理状态退回：业务上已回到客服侧，由创建者或客服团队退回
    if (from_state, to_state) in [("resolved", "open"), ("resolved", "on_hold")]:
        if ticket.creator_id == user.id:
            return
        if user.role == "agent":
            return
        raise ForbiddenError("只有创建者或客服团队可退回已处理工单")

    # 撤销：仅创建者（发起人）
    if to_state == "cancelled" and from_state in ("pending", "open", "on_hold", "returned"):
        if ticket.creator_id == user.id:
            return
        raise ForbiddenError("只有工单发起人可撤销工单")

    # 客服团队操作：归档
    if (from_state, to_state) in [("resolved", "archived")]:
        if user.role != "agent":
            raise ForbiddenError("只有客服团队可执行归档操作")
        return

    # 待受理退回：部门对接人 → 已退回，处理人给创建者
    if from_state == "pending" and to_state == "returned":
        if await is_dispatcher(db, user.id, ticket.skill_group_id):
            return
        raise ForbiddenError("只有部门对接人可退回待受理工单")

    # 已退回工单：创建者可重新提交或撤销
    if from_state == "returned" and to_state in ("pending", "cancelled"):
        if ticket.creator_id == user.id:
            return
        raise ForbiddenError("只有创建者可处理已退回工单")

    raise ForbiddenError("无权执行此状态变更")


async def apply_initial_state(
    db: AsyncSession,
    ticket: Ticket,
    *,
    to_state: str,
    operator: User,
    reason: str | None = None,
    body=None,
) -> TicketStateLog:
    """建单 / 草稿提交 / 即时办结的初始状态落库：None → pending / archived。

    与 apply_transition 共享同一套公共实现：
      - 初始态合法性：validate_initial_state（仅 pending / archived）
      - 终态副作用：closed_at / closed_duration_minutes（即时办结 → archived）
      - Flow Log：from_state=None、停留时长为 None、人员快照
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
        **snapshot_people(ticket, body),
    )
    db.add(log)
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
) -> TicketStateLog | None:
    """单条工单状态流转的唯一执行入口。

    收口顺序（与原 update_ticket 单条 PATCH 语义一致）：
      1. 业务约束改写（resolved→on_hold → open）
      2. validate_transition（合法性）
      3. check_transition_permission（角色/身份权限 + 分派须指定处理人）
      4. requires_reason（退回/暂缓/撤销必须填原因）
      5. 状态副作用（first_owner/solved_at/resolved/SLA breach/owner 清理/
         returned_to_user/closed_at/closed_duration_minutes/hold_until）
      6. 应用调用方给出的人员字段（显式值优先于副作用）
      7. has_returned 同步 + 写 Flow Log（含上一状态停留时长与人员快照）

    返回写入的 TicketStateLog；to_state 与当前状态相同（no-op）时返回 None。
    不负责 commit——由调用方按各自的请求边界提交。
    """
    # 1. 业务约束
    to_state = enforce_business_constraints(ticket, to_state)
    if to_state == ticket.state:
        return None

    # 2. 合法性
    validate_transition(ticket.state, to_state)

    # 3. 权限
    await check_transition_permission(db, ticket, to_state, operator, owner_id)

    # 4. 原因必填
    if requires_reason(ticket.state, to_state) and not reason:
        raise HTTPException(
            400,
            detail=(
                f"从「{STATE_LABELS.get(ticket.state, ticket.state)}」"
                f"变更为「{STATE_LABELS.get(to_state, to_state)}」需要填写原因"
            ),
        )

    old_state = ticket.state
    now = datetime.now(timezone.utc)

    # 5. 状态副作用
    if to_state == "open":
        if old_state == "pending":
            # 分派处理人：pending→open 时由对接人指定 owner_id；
            # first_owner 记录被指派的首任处理人，无人可退时记操作人
            ticket.first_owner_id = (owner_id if owner_id is not None else ticket.owner_id) or operator.id
        elif old_state == "returned":
            # 已退回工单重新提交：保持无处理人，等待再次分派
            ticket.returned_to_user_id = None
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

    # 6. 显式人员字段（覆盖副作用，与原 PATCH 语义一致）
    if owner_id is not None:
        ticket.owner_id = owner_id
    if dispatcher_id is not None:
        ticket.dispatcher_id = dispatcher_id

    # 暂缓：存 hold_until
    if to_state == "on_hold" and hold_until:
        ticket.hold_until = datetime.fromisoformat(hold_until).replace(tzinfo=timezone.utc)

    # has_returned 跟随"最新一次动作"：属于 RETURN_TRANSITIONS 才置 true
    ticket.has_returned = (old_state, to_state) in RETURN_TRANSITIONS
    ticket.state = to_state

    # 上一状态停留时长
    last_log = await db.execute(
        select(TicketStateLog)
        .where(TicketStateLog.ticket_id == ticket.id)
        .order_by(TicketStateLog.created_at.desc()).limit(1)
    )
    last = last_log.scalar_one_or_none()
    duration = int((now - last.created_at).total_seconds() / 60) if last else None

    # Flow Log（快照取的是 ticket 已应用新值后的人员）
    log = TicketStateLog(
        ticket_id=ticket.id, from_state=old_state, to_state=to_state,
        operator_id=operator.id, reason=reason, duration_minutes=duration,
        **snapshot_people(ticket),
    )
    db.add(log)
    await db.flush()
    return log
