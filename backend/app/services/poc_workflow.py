"""POC 质量问题闭环：动作服务、权限矩阵与数据范围。

所有状态流转只能经由 `execute_action()`，禁止通过 PATCH 直接改状态、
分系统、负责人或批准人。

契约依据：docs/poc/00_poc_workflow_development_contract.md
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import ColumnElement, false, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.domain.poc_workflow import (
    ACTION_ORDER,
    ACTION_RULES,
    ActionRule,
    ActorScope,
    BusinessRole,
    Priority,
    TicketAction,
    TicketState,
    TERMINAL_STATES,
    VerificationStatus,
    actions_for_state,
    is_terminal,
    responsible_role_for,
    responsible_user_field_for,
)
from app.models.ticket import Ticket

logger = logging.getLogger("poc.workflow")

TERMINAL_VALUES = frozenset(state.value for state in TERMINAL_STATES)


# ── 小工具 ─────────────────────────────────────────────────


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _as_aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _has_text(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def actor_skill_group_ids(actor: Any) -> list[int]:
    groups = getattr(actor, "skill_groups", None) or []
    return [g.id for g in groups if g is not None]


def actor_roles(actor: Any) -> set[str]:
    """操作人拥有的全部业务角色编码（多角色）。"""
    roles = getattr(actor, "roles", None)
    if roles is None:
        # 兜底：极端情况下传入的是轻量对象
        return set()
    return set(roles)


def actor_has_role(actor: Any, *roles: BusinessRole | str) -> bool:
    owned = actor_roles(actor)
    return any(
        (role.value if isinstance(role, BusinessRole) else role) in owned
        for role in roles
    )


# ── 数据范围 ───────────────────────────────────────────────


def ticket_scope(actor: Any) -> ColumnElement | None:
    """角色数据范围条件。返回 None 表示不受限（admin/quality）。

    多角色用户取各角色数据范围的**并集**。
    列表、详情、附件下载、导出必须复用同一条件。
    """
    roles = actor_roles(actor)
    if not roles:
        return false()
    if roles & {BusinessRole.ADMIN.value, BusinessRole.QUALITY.value}:
        return None

    conditions: list[ColumnElement] = []
    if BusinessRole.TASKFORCE.value in roles:
        # 专项小组：全部未闭环问题，用于判断涉及分系统
        conditions.append(Ticket.state.notin_(TERMINAL_VALUES))
    if BusinessRole.PRESALES.value in roles:
        conditions.append(Ticket.creator_id == actor.id)
    if BusinessRole.APPROVER.value in roles:
        conditions.append(Ticket.approver_id == actor.id)
    if BusinessRole.SUBSYSTEM.value in roles:
        conditions.append(Ticket.subsystem_owner_id == actor.id)
        skill_group_ids = actor_skill_group_ids(actor)
        if skill_group_ids:
            conditions.append(Ticket.skill_group_id.in_(skill_group_ids))
    if not conditions:
        return false()
    return or_(*conditions)


def can_view(ticket: Any, actor: Any) -> bool:
    """单条可见性判断，规则与 ticket_scope() 保持一致（多角色取并集）。"""
    roles = actor_roles(actor)
    if getattr(ticket, "is_draft", False):
        return ticket.creator_id == actor.id or BusinessRole.ADMIN.value in roles
    if roles & {BusinessRole.ADMIN.value, BusinessRole.QUALITY.value}:
        return True
    if BusinessRole.TASKFORCE.value in roles and ticket.state not in TERMINAL_VALUES:
        return True
    if BusinessRole.PRESALES.value in roles and ticket.creator_id == actor.id:
        return True
    if BusinessRole.APPROVER.value in roles and ticket.approver_id == actor.id:
        return True
    if BusinessRole.SUBSYSTEM.value in roles:
        if ticket.subsystem_owner_id == actor.id:
            return True
        if ticket.skill_group_id in actor_skill_group_ids(actor):
            return True
    return False


def ensure_can_view(ticket: Any, actor: Any) -> None:
    if not can_view(ticket, actor):
        raise ForbiddenError("无权查看该问题")


# ── 权限矩阵 ───────────────────────────────────────────────


def _return_target_matches(ticket: Any, actor: Any) -> bool:
    target = ticket.return_to_state
    if target == TicketState.PENDING_APPROVAL.value:
        return actor_has_role(actor, BusinessRole.PRESALES) and ticket.creator_id == actor.id
    if target in (TicketState.PLANNING.value, TicketState.PROCESSING.value):
        return (
            actor_has_role(actor, BusinessRole.SUBSYSTEM)
            and ticket.subsystem_owner_id == actor.id
        )
    return False


def _scope_matches(rule: ActionRule, ticket: Any, actor: Any) -> bool:
    if rule.scope is ActorScope.ROLE:
        return True
    if rule.scope is ActorScope.ASSIGNED_APPROVER:
        return ticket.approver_id == actor.id
    if rule.scope is ActorScope.CREATOR:
        return ticket.creator_id == actor.id
    if rule.scope is ActorScope.SUBSYSTEM_OWNER:
        return ticket.subsystem_owner_id == actor.id
    if rule.scope is ActorScope.RETURN_TARGET:
        return _return_target_matches(ticket, actor)
    return False


def _rule_permits(rule: ActionRule, ticket: Any, actor: Any) -> bool:
    """多角色：拥有动作要求的任一角色 + 满足人员范围即可。"""
    if actor_has_role(actor, BusinessRole.ADMIN):
        return True  # 管理员兜底
    if not (actor_roles(actor) & {r.value for r in rule.roles}):
        return False
    return _scope_matches(rule, ticket, actor)


def allowed_actions(ticket: Any, actor: Any) -> list[str]:
    """当前操作人现在可以执行的动作编码列表（后端二次校验，不信任前端）。"""
    try:
        state = TicketState(ticket.state)
    except ValueError:
        return []
    if state in TERMINAL_STATES:
        return []
    if getattr(ticket, "is_draft", False):
        return []

    candidates: list[TicketAction] = list(actions_for_state(state))
    if actor_has_role(actor, BusinessRole.ADMIN) and TicketAction.CANCEL not in candidates:
        candidates.append(TicketAction.CANCEL)

    permitted = [
        action
        for action in candidates
        if _rule_permits_for_action(action, ticket, actor)
    ]
    return [a.value for a in sorted(permitted, key=ACTION_ORDER.index)]


def _rule_permits_for_action(action: TicketAction, ticket: Any, actor: Any) -> bool:
    rule = ACTION_RULES.get((TicketState(ticket.state), action))
    is_admin = actor_has_role(actor, BusinessRole.ADMIN)
    if rule is None:
        # 管理员兜底撤销：任意非终态
        return action is TicketAction.CANCEL and is_admin and not is_terminal(ticket.state)
    if action is TicketAction.CANCEL and is_admin:
        return True
    return _rule_permits(rule, ticket, actor)


def responsible_role(ticket: Any) -> str | None:
    role = responsible_role_for(ticket.state, ticket.return_to_state)
    return role.value if role else None


def responsible_user_id(ticket: Any) -> int | None:
    field = responsible_user_field_for(ticket.state, ticket.return_to_state)
    return getattr(ticket, field, None) if field else None


def compute_is_overdue(ticket: Any, now: datetime | None = None) -> bool:
    """未闭环且已超过计划完成时间即逾期。"""
    if ticket.state in TERMINAL_VALUES:
        return False
    planned = _as_aware(ticket.planned_completion_at)
    if planned is None:
        return False
    return planned < (now or now_utc())


# ── 动作执行 ───────────────────────────────────────────────


def _text(payload: dict, comment: str | None, field: str, default=None):
    value = payload.get(field)
    if _has_text(value):
        return value
    return comment if comment else default


def _parse_datetime(value: Any, field: str) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return _as_aware(value)
    if isinstance(value, str):
        try:
            return _as_aware(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            raise HTTPException(422, detail=f"字段 {field} 不是合法的 ISO 时间")
    raise HTTPException(422, detail=f"字段 {field} 不是合法的 ISO 时间")


def _parse_int(value: Any, field: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        raise HTTPException(422, detail=f"字段 {field} 必须是整数")


def _require_fields(ticket: Any, payload: dict, fields: tuple[str, ...]) -> None:
    """必填校验：payload 优先，其次取工单上已有值。"""
    missing = [
        field
        for field in fields
        if not _has_text(payload.get(field) if field in payload else getattr(ticket, field, None))
    ]
    if missing:
        raise HTTPException(400, detail="缺少业务必填字段：" + "、".join(missing))


async def _apply_route(db: AsyncSession, ticket: Any, payload: dict) -> None:
    from app.models.group import SkillGroup, UserSkillGroup
    from app.models.user import User

    skill_group_id = _parse_int(payload.get("skill_group_id"), "skill_group_id")
    owner_id = _parse_int(payload.get("subsystem_owner_id"), "subsystem_owner_id")

    skill_group = await db.get(SkillGroup, skill_group_id)
    if skill_group is None:
        raise NotFoundError("分系统", skill_group_id)

    owner = await db.get(User, owner_id)
    if owner is None or not owner.is_active:
        raise NotFoundError("用户", owner_id)
    if not owner.has_role(BusinessRole.SUBSYSTEM):
        raise HTTPException(400, detail="分系统负责人必须拥有 subsystem 角色")

    membership = await db.execute(
        select(UserSkillGroup).where(
            UserSkillGroup.user_id == owner.id,
            UserSkillGroup.skill_group_id == skill_group.id,
        )
    )
    if membership.scalar_one_or_none() is None:
        raise HTTPException(400, detail="该用户不属于所选分系统")

    ticket.skill_group_id = skill_group.id
    ticket.subsystem_owner_id = owner.id


def _resolve_return_target(ticket: Any, rule: ActionRule, payload: dict) -> TicketState:
    if rule.fixed_return_to is not None:
        requested = payload.get("return_to_state")
        if requested is not None and requested != rule.fixed_return_to.value:
            raise HTTPException(400, detail="该动作的退回目标由当前节点固定决定")
        return rule.fixed_return_to

    requested = payload.get("return_to_state")
    if not _has_text(requested):
        # 第一阶段每个退回节点只有一个合法目标，缺省按规则推导
        if len(rule.return_targets) == 1:
            return next(iter(rule.return_targets))
        raise HTTPException(400, detail="退回必须指定 return_to_state")

    try:
        target = TicketState(requested)
    except ValueError:
        raise HTTPException(422, detail=f"return_to_state 取值非法：{requested}")
    if target not in rule.return_targets:
        raise HTTPException(400, detail=f"当前节点不允许退回到 {target.value}")
    return target


async def execute_action(
    db: AsyncSession,
    ticket: Any,
    actor: Any,
    action: TicketAction | str,
    payload: dict | None = None,
    comment: str | None = None,
    expected_version: int | None = None,
) -> Any:
    """执行一个流程动作。校验顺序固定，任一步失败即整单不落库。"""
    from app.models.ticket import TicketStateLog

    payload = dict(payload or {})
    comment = comment.strip() if isinstance(comment, str) and comment.strip() else None

    # 1. 终态校验
    try:
        state = TicketState(ticket.state)
    except ValueError:
        raise HTTPException(400, detail=f"工单状态 {ticket.state} 不属于 POC 流程")
    if state in TERMINAL_STATES:
        raise HTTPException(400, detail="工单已处于终态，不能再执行流程动作")

    try:
        action = TicketAction(action)
    except ValueError:
        raise HTTPException(422, detail=f"未知动作：{action}")

    # 2. 并发版本校验
    if expected_version is not None and int(expected_version) != ticket.state_version:
        raise ConflictError(
            f"问题已被他人更新（当前版本 {ticket.state_version}），请刷新后重试"
        )

    # 3. 状态是否允许该动作
    rule = ACTION_RULES.get((state, action))
    admin_cancel = (
        rule is None
        and action is TicketAction.CANCEL
        and actor_has_role(actor, BusinessRole.ADMIN)
    )
    if rule is None and not admin_cancel:
        raise HTTPException(
            400, detail=f"当前状态「{state.value}」不支持动作「{action.value}」"
        )
    if admin_cancel:
        rule = ActionRule(
            target_state=TicketState.CANCELLED,
            roles=frozenset({BusinessRole.ADMIN}),
            comment_required=True,
        )

    # 4/5. 角色与人员范围（多角色：任一角色满足即可）
    if not actor_has_role(actor, BusinessRole.ADMIN):
        if not (actor_roles(actor) & {r.value for r in rule.roles}):
            raise ForbiddenError(
                f"角色 {'/'.join(sorted(actor_roles(actor))) or '未知'} 无权执行动作 {action.value}"
            )
        if not _scope_matches(rule, ticket, actor):
            raise ForbiddenError("你不是该问题当前节点的指定责任人")

    # 6. payload 字段白名单 + 必填校验
    unknown = sorted(set(payload) - set(rule.payload_fields))
    if unknown:
        raise HTTPException(422, detail="不支持的字段：" + "、".join(unknown))
    if rule.comment_required and not comment:
        raise HTTPException(400, detail="该动作必须填写意见/原因")
    _require_fields(ticket, payload, rule.required_fields)

    old_state = state
    target_state = rule.target_state
    return_target: TicketState | None = None

    # 7. 写入业务字段
    if action is TicketAction.APPROVE:
        pass
    elif action is TicketAction.CONFIRM_PROBLEM:
        ticket.confirmation_comment = _text(payload, comment, "confirmation_comment")
    elif action is TicketAction.ROUTE:
        await _apply_route(db, ticket, payload)
    elif action is TicketAction.ACCEPT:
        ticket.acceptance_comment = _text(payload, comment, "acceptance_comment")
    elif action is TicketAction.SUBMIT_PLAN:
        if payload.get("temporary_measure") is not None:
            ticket.temporary_measure = payload["temporary_measure"] or None
        if payload.get("long_term_measure") is not None:
            ticket.long_term_measure = payload["long_term_measure"]
        if payload.get("planned_completion_at") is not None:
            ticket.planned_completion_at = _parse_datetime(
                payload["planned_completion_at"], "planned_completion_at"
            )
    elif action is TicketAction.CONFIRM_PLAN:
        ticket.plan_confirmation_comment = _text(
            payload, comment, "plan_confirmation_comment"
        )
    elif action is TicketAction.SUBMIT_ANALYSIS:
        if payload.get("initial_investigation") is not None:
            ticket.initial_investigation = payload["initial_investigation"]
        if payload.get("root_cause") is not None:
            ticket.root_cause = payload["root_cause"]
        if payload.get("analysis_report") is not None:
            ticket.analysis_report = payload["analysis_report"]
        ticket.actual_completion_at = now_utc()
    elif action is TicketAction.PASS_REVIEW:
        raw_status = payload.get("verification_status", ticket.verification_status)
        try:
            ticket.verification_status = VerificationStatus(raw_status).value
        except ValueError:
            raise HTTPException(
                422,
                detail="verification_status 取值必须是 "
                + "/".join(v.value for v in VerificationStatus),
            )
        if payload.get("verification_conclusion") is not None:
            ticket.verification_conclusion = payload["verification_conclusion"]
        if payload.get("quality_review_result") is not None:
            ticket.quality_review_result = payload["quality_review_result"]
    elif action is TicketAction.REGISTER_DEFECT:
        if payload.get("defect_id") is not None:
            ticket.defect_id = str(payload["defect_id"]).strip()
        if payload.get("defect_repository_path") is not None:
            ticket.defect_repository_path = str(payload["defect_repository_path"]).strip()
        ticket.defect_registered_at = now_utc()
        ticket.defect_registered_by_id = actor.id
    elif action in (TicketAction.REJECT, TicketAction.RETURN):
        # 先进入 returned 展示状态，退回目标写入 return_to_state
        return_target = _resolve_return_target(ticket, rule, payload)
    elif action is TicketAction.RESUBMIT:
        target_state = _resubmit_target(ticket)
    elif action is TicketAction.CANCEL:
        target_state = TicketState.CANCELLED

    if target_state is None:  # 理论上不可达
        raise HTTPException(400, detail="无法确定目标状态")

    # 8/9. 状态与版本
    ticket.state = target_state.value
    if target_state is TicketState.RETURNED:
        ticket.return_to_state = return_target.value if return_target else None
    else:
        ticket.return_to_state = None
    if target_state in TERMINAL_STATES:
        ticket.closed_at = ticket.closed_at or now_utc()
    ticket.state_version = (ticket.state_version or 1) + 1
    ticket.updated_at = now_utc()

    # 10. 不可变流程日志
    last_log = (
        await db.execute(
            select(TicketStateLog)
            .where(TicketStateLog.ticket_id == ticket.id)
            .order_by(TicketStateLog.id.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    duration = None
    if last_log is not None and last_log.created_at is not None:
        duration = int(
            (now_utc() - _as_aware(last_log.created_at)).total_seconds() / 60
        )

    db.add(
        TicketStateLog(
            ticket_id=ticket.id,
            from_state=old_state.value,
            to_state=target_state.value,
            operator_id=actor.id,
            action=action.value,
            comment=comment,
            reason=comment,
            payload_snapshot=payload or None,
            state_version=ticket.state_version,
            responsible_role_snapshot=responsible_role(ticket),
            responsible_user_id_snapshot=responsible_user_id(ticket),
            duration_minutes=duration,
        )
    )

    await db.flush()
    await db.commit()

    logger.info(
        "poc action executed: ticket_id=%s action=%s %s->%s operator=%s version=%s",
        ticket.id,
        action.value,
        old_state.value,
        target_state.value,
        actor.id,
        ticket.state_version,
    )

    # 11. 事务成功后通知下一责任人；通知失败不回滚业务动作
    try:
        from app.services.notification import notify_poc_action

        await notify_poc_action(db, ticket, action, actor, old_state, target_state)
        await db.commit()
    except Exception:  # noqa: BLE001 - 通知失败绝不阻断业务
        await db.rollback()
        logger.exception("POC 流程通知发送失败，业务动作已提交：ticket_id=%s", ticket.id)

    return ticket


def _resubmit_target(ticket: Any) -> TicketState:
    if not _has_text(ticket.return_to_state):
        raise HTTPException(400, detail="工单缺少 return_to_state，无法重新提交")
    try:
        target = TicketState(ticket.return_to_state)
    except ValueError:
        raise HTTPException(400, detail="return_to_state 取值非法")
    allowed = {
        TicketState.PENDING_APPROVAL,
        TicketState.PLANNING,
        TicketState.PROCESSING,
    }
    if target not in allowed:
        raise HTTPException(400, detail=f"不允许重新提交到 {target.value}")
    return target


def verify_approver(user: Any) -> None:
    """校验用户是有效批准人。"""
    if user is None or not user.is_active:
        raise NotFoundError("批准人")
    if not user.has_role(BusinessRole.APPROVER):
        raise HTTPException(400, detail="approver_id 必须指向拥有 approver 角色的用户")


def next_priority(value: Any) -> str:
    try:
        return Priority(value).value
    except ValueError:
        raise HTTPException(
            422,
            detail="priority 取值必须是 " + "/".join(p.value for p in Priority),
        )


__all__ = [
    "allowed_actions",
    "can_view",
    "compute_is_overdue",
    "ensure_can_view",
    "execute_action",
    "next_priority",
    "now_utc",
    "responsible_role",
    "responsible_user_id",
    "ticket_scope",
    "verify_approver",
]
