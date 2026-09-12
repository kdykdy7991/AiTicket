"""POC 质量问题闭环工单 API。

所有状态流转只能走 `POST /tickets/{id}/actions`；
`PATCH /tickets/{id}` 只允许当前责任人在规定节点修改规定字段，
且永远不能修改 state / 分系统 / 负责人 / 批准人。
"""

from __future__ import annotations

import csv
import io
import logging
from datetime import datetime, time, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, require_any_role
from app.core.exceptions import ForbiddenError, NotFoundError
from app.domain.poc_workflow import (
    BusinessRole,
    Priority,
    TicketState,
    VerificationStatus,
)
from app.models.ticket import Ticket, TicketAttachment, TicketStateLog
from app.models.user import User
from app.schemas.ticket import (
    ANALYSIS_EDITABLE_FIELDS,
    CREATION_EDITABLE_FIELDS,
    CREATE_REQUIRED_FIELDS,
    PLAN_EDITABLE_FIELDS,
    DraftSubmitRequest,
    TicketActionRequest,
    TicketAttachmentOut,
    TicketBrief,
    TicketCreate,
    TicketCreateResponse,
    TicketDetail,
    TicketStateLogOut,
    TicketUpdate,
)
from app.services.poc_workflow import (
    TERMINAL_VALUES,
    allowed_actions,
    compute_is_overdue,
    ensure_can_view,
    execute_action,
    next_priority,
    now_utc,
    responsible_role,
    responsible_user_id as current_responsible_user_id,
    state_label,
    ticket_scope,
    verify_approver,
)

logger = logging.getLogger("poc.api.tickets")

router = APIRouter(tags=["tickets"])

DETAIL_LOAD_OPTIONS = (
    selectinload(Ticket.attachments).selectinload(TicketAttachment.uploader),
    selectinload(Ticket.state_logs).selectinload(TicketStateLog.operator),
    selectinload(Ticket.state_logs).selectinload(TicketStateLog.responsible_user_snapshot),
)

ROLE_LABELS = {
    BusinessRole.PRESALES.value: "售前",
    BusinessRole.APPROVER.value: "批准人",
    BusinessRole.TASKFORCE.value: "专项小组",
    BusinessRole.SUBSYSTEM.value: "分系统",
    BusinessRole.QUALITY.value: "质量",
    BusinessRole.ADMIN.value: "系统管理员",
}


# ── 序列化 ─────────────────────────────────────────────────


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def _people(ticket: Ticket) -> dict[int, str]:
    mapping: dict[int, str] = {}
    for attr in ("creator", "approver", "subsystem_owner"):
        person = getattr(ticket, attr, None)
        if person is not None:
            mapping[person.id] = person.name
    return mapping


def _brief(ticket: Ticket) -> TicketBrief:
    role = responsible_role(ticket)
    uid = current_responsible_user_id(ticket)
    return TicketBrief(
        id=ticket.id,
        number=ticket.number,
        title=ticket.title,
        proposer=ticket.proposer,
        proposer_department=ticket.proposer_department,
        product_line=ticket.product_line,
        customer_name=ticket.customer_name,
        priority=ticket.priority,
        problem_type=ticket.problem_type,
        state=ticket.state,
        state_version=ticket.state_version or 1,
        is_draft=bool(ticket.is_draft),
        return_to_state=ticket.return_to_state,
        current_responsible_role=role,
        current_responsible_user_id=uid,
        current_responsible_user_name=_people(ticket).get(uid) if uid else None,
        creator_id=ticket.creator_id,
        creator_name=ticket.creator.name if ticket.creator else None,
        creator_department=ticket.creator_department,
        approver_id=ticket.approver_id,
        approver_name=ticket.approver.name if ticket.approver else None,
        skill_group_id=ticket.skill_group_id,
        skill_group_name=ticket.skill_group.name if ticket.skill_group else None,
        subsystem_owner_id=ticket.subsystem_owner_id,
        subsystem_owner_name=ticket.subsystem_owner.name if ticket.subsystem_owner else None,
        planned_completion_at=ticket.planned_completion_at,
        actual_completion_at=ticket.actual_completion_at,
        is_overdue=compute_is_overdue(ticket),
        verification_status=ticket.verification_status,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


def _attachment_out(att: TicketAttachment) -> TicketAttachmentOut:
    return TicketAttachmentOut(
        id=att.id,
        ticket_id=att.ticket_id,
        original_filename=att.original_filename,
        content_type=att.content_type,
        size=att.size,
        stage=att.stage,
        uploader_id=att.uploader_id,
        uploader_name=att.uploader.name if att.uploader else None,
        download_url=f"/api/v1/attachments/{att.id}/download",
        created_at=att.created_at,
    )


def _log_out(log: TicketStateLog) -> TicketStateLogOut:
    return TicketStateLogOut(
        id=log.id,
        action=log.action,
        from_state=log.from_state,
        to_state=log.to_state,
        operator_id=log.operator_id,
        operator_name=log.operator.name if log.operator else None,
        operator_roles=log.operator.roles if log.operator else [],
        comment=log.comment,
        payload=log.payload_snapshot,
        responsible_role_snapshot=log.responsible_role_snapshot,
        responsible_user_id_snapshot=log.responsible_user_id_snapshot,
        responsible_user_name_snapshot=(
            log.responsible_user_snapshot.name if log.responsible_user_snapshot else None
        ),
        state_version=log.state_version,
        created_at=log.created_at,
    )


def _detail(ticket: Ticket, actor: User) -> TicketDetail:
    brief = _brief(ticket)
    return TicketDetail(
        **brief.model_dump(),
        closure_requirement=ticket.closure_requirement,
        occurred_at=ticket.occurred_at,
        location=ticket.location,
        longitude=float(ticket.longitude) if ticket.longitude is not None else None,
        latitude=float(ticket.latitude) if ticket.latitude is not None else None,
        device_info=ticket.device_info,
        description=ticket.description,
        confirmation_comment=ticket.confirmation_comment,
        temporary_measure=ticket.temporary_measure,
        long_term_measure=ticket.long_term_measure,
        plan_confirmation_comment=ticket.plan_confirmation_comment,
        initial_investigation=ticket.initial_investigation,
        root_cause=ticket.root_cause,
        analysis_report=ticket.analysis_report,
        verification_conclusion=ticket.verification_conclusion,
        quality_review_result=ticket.quality_review_result,
        closed_at=ticket.closed_at,
        allowed_actions=allowed_actions(ticket, actor),
        attachments=[_attachment_out(a) for a in (ticket.attachments or [])],
        state_logs=[_log_out(log) for log in (ticket.state_logs or [])],
    )


async def _load_detail(db: AsyncSession, ticket_id: int) -> Ticket:
    """按详情需要加载工单；不存在时返回 404（不能抛 NoResultFound 变成 500）。

    populate_existing 用于强制刷新同一 session 里已被读取过的实例
    （动作执行后需要拿到最新的 state_logs / attachments）。
    """
    result = await db.execute(
        select(Ticket)
        .options(*DETAIL_LOAD_OPTIONS)
        .where(Ticket.id == ticket_id)
        .execution_options(populate_existing=True)
    )
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("问题", ticket_id)
    return ticket


async def _get_ticket_or_404(db: AsyncSession, ticket_id: int, *, lock: bool = False) -> Ticket:
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    if lock:
        stmt = stmt.with_for_update()
    ticket = (await db.execute(stmt)).scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("问题", ticket_id)
    return ticket


# ── 建单辅助 ───────────────────────────────────────────────


def _apply_create_fields(ticket: Ticket, body) -> None:
    for field in (
        "title",
        "proposer",
        "proposer_department",
        "product_line",
        "customer_name",
        "problem_type",
        "closure_requirement",
        "occurred_at",
        "location",
        "longitude",
        "latitude",
        "device_info",
        "description",
        "approver_id",
    ):
        value = getattr(body, field, None)
        if value is None:
            continue
        if field in ("occurred_at", "planned_completion_at"):
            value = _aware(value)
        setattr(ticket, field, value)
    if getattr(body, "priority", None) is not None:
        ticket.priority = next_priority(body.priority)


def _missing_create_fields(ticket: Ticket) -> list[str]:
    missing = []
    for field in CREATE_REQUIRED_FIELDS:
        value = getattr(ticket, field, None)
        if value is None or (isinstance(value, str) and not value.strip()):
            missing.append(field)
    return missing


async def _validate_formal_submit(db: AsyncSession, ticket: Ticket) -> None:
    missing = _missing_create_fields(ticket)
    if missing:
        raise HTTPException(400, detail="缺少业务必填字段：" + "、".join(missing))
    if ticket.approver_id is None:
        raise HTTPException(400, detail="缺少业务必填字段：approver_id")
    approver = await db.get(User, ticket.approver_id)
    verify_approver(approver)


async def _generate_number(db: AsyncSession) -> str:
    today = datetime.now().strftime("%Y%m%d")
    max_number = (
        await db.execute(
            select(func.max(Ticket.number)).where(Ticket.number.like(f"{today}-%"))
        )
    ).scalar()
    seq = int(max_number.split("-")[-1]) + 1 if max_number else 1
    return f"{today}-{seq:04d}"


def _new_ticket(user: User, *, is_draft: bool) -> Ticket:
    return Ticket(
        number=None,
        is_draft=is_draft,
        state=TicketState.PENDING_APPROVAL.value,
        state_version=1,
        priority=Priority.P2_NORMAL.value,
        description="",
        creator_id=user.id,
        creator_department=(user.group.name if getattr(user, "group", None) else None),
        legacy_state=None,
    )


def _write_initial_log(ticket: Ticket, user: User, comment: str | None = None) -> TicketStateLog:
    return TicketStateLog(
        ticket_id=ticket.id,
        from_state=None,
        to_state=ticket.state,
        operator_id=user.id,
        action=None,
        comment=comment,
        reason=comment,
        payload_snapshot=None,
        state_version=ticket.state_version,
        responsible_role_snapshot=responsible_role(ticket),
        responsible_user_id_snapshot=current_responsible_user_id(ticket),
    )


async def _respond_detail(db: AsyncSession, ticket_id: int, actor: User) -> TicketDetail:
    return _detail(await _load_detail(db, ticket_id), actor)


# ── 基础查询构造 ───────────────────────────────────────────


def _base_query(user: User):
    """POC 工单基础查询：排除草稿与非 POC 历史数据，并套用角色数据范围。"""
    query = select(Ticket).where(
        Ticket.is_draft == False,  # noqa: E712
        Ticket.legacy_state.is_(None),
    )
    scope = ticket_scope(user)
    if scope is not None:
        query = query.where(scope)
    return query


def _apply_filters(
    query,
    *,
    state: list[TicketState] | None,
    priority: list[Priority] | None,
    skill_group_id: int | None,
    responsible_user_id_filter: int | None,
    verification_status: VerificationStatus | None,
    is_overdue: bool | None,
    keyword: str | None,
    date_from: str | None,
    date_to: str | None,
):
    if state:
        query = query.where(Ticket.state.in_([s.value for s in state]))
    if priority:
        query = query.where(Ticket.priority.in_([p.value for p in priority]))
    if skill_group_id:
        query = query.where(Ticket.skill_group_id == skill_group_id)
    if verification_status:
        query = query.where(Ticket.verification_status == verification_status.value)
    if responsible_user_id_filter:
        uid = responsible_user_id_filter
        query = query.where(
            or_(
                (Ticket.state == TicketState.PENDING_APPROVAL.value)
                & (Ticket.approver_id == uid),
                (
                    Ticket.state.in_(
                        [
                            TicketState.PLANNING.value,
                            TicketState.PROCESSING.value,
                        ]
                    )
                )
                & (Ticket.subsystem_owner_id == uid),
                (Ticket.state == TicketState.PENDING_PLAN_CONFIRMATION.value)
                & (Ticket.creator_id == uid),
                (Ticket.state == TicketState.RETURNED.value)
                & (Ticket.return_to_state == TicketState.PENDING_APPROVAL.value)
                & (Ticket.creator_id == uid),
                (Ticket.state == TicketState.RETURNED.value)
                & (
                    Ticket.return_to_state.in_(
                        [TicketState.PLANNING.value, TicketState.PROCESSING.value]
                    )
                )
                & (Ticket.subsystem_owner_id == uid),
            )
        )
    if is_overdue is not None:
        now = now_utc()
        overdue = (
            Ticket.planned_completion_at.is_not(None)
            & (Ticket.planned_completion_at < now)
            & Ticket.state.notin_(TERMINAL_VALUES)
        )
        query = query.where(overdue if is_overdue else ~overdue)
    if keyword:
        like = f"%{keyword}%"
        query = query.where(
            Ticket.number.ilike(like)
            | Ticket.title.ilike(like)
            | Ticket.proposer.ilike(like)
            | Ticket.proposer_department.ilike(like)
            | Ticket.product_line.ilike(like)
            | Ticket.customer_name.ilike(like)
            | Ticket.problem_type.ilike(like)
            | Ticket.description.ilike(like)
        )
    if date_from:
        try:
            d = datetime.strptime(date_from, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(422, detail="date_from 格式错误，应为 YYYY-MM-DD")
        query = query.where(Ticket.created_at >= datetime.combine(d, time.min))
    if date_to:
        try:
            d = datetime.strptime(date_to, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(422, detail="date_to 格式错误，应为 YYYY-MM-DD")
        query = query.where(Ticket.created_at <= datetime.combine(d, time.max))
    return query


# ── 建单 / 草稿 ────────────────────────────────────────────


@router.post(
    "/tickets",
    response_model=TicketCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_ticket(
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(
        require_any_role(BusinessRole.PRESALES.value, BusinessRole.ADMIN.value)
    ),
):
    """新建问题；`is_draft=true` 保存草稿，否则直接进入 `pending_approval`。"""
    ticket = _new_ticket(user, is_draft=body.is_draft)
    _apply_create_fields(ticket, body)

    warnings = None
    if body.is_draft:
        db.add(ticket)
        await db.flush()
    else:
        await _validate_formal_submit(db, ticket)
        ticket.number = await _generate_number(db)
        ticket.is_draft = False
        db.add(ticket)
        await db.flush()
        db.add(_write_initial_log(ticket, user, comment="提交审批"))

    await db.commit()
    detail = await _respond_detail(db, ticket.id, user)
    return TicketCreateResponse(data=detail, warnings=warnings)


@router.get("/tickets/drafts")
async def list_drafts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """当前用户的草稿。"""
    result = await db.execute(
        select(Ticket)
        .where(
            Ticket.is_draft == True,  # noqa: E712
            Ticket.creator_id == user.id,
            Ticket.legacy_state.is_(None),
        )
        .order_by(Ticket.updated_at.desc())
    )
    tickets = result.scalars().all()
    return {
        "data": [_brief(t).model_dump() for t in tickets],
        "pagination": {"total": len(tickets)},
    }


@router.patch("/tickets/drafts/{draft_id}", response_model=TicketCreateResponse)
async def update_draft(
    draft_id: int,
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ticket = await _get_ticket_or_404(db, draft_id)
    if not ticket.is_draft or ticket.creator_id != user.id:
        raise NotFoundError("草稿", draft_id)
    _apply_create_fields(ticket, body)
    await db.commit()
    return TicketCreateResponse(data=await _respond_detail(db, draft_id, user))


@router.delete("/tickets/drafts/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    draft_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ticket = await _get_ticket_or_404(db, draft_id)
    if not ticket.is_draft or ticket.creator_id != user.id:
        raise NotFoundError("草稿", draft_id)
    await db.delete(ticket)
    await db.commit()


@router.post("/tickets/drafts/{draft_id}/submit", response_model=TicketCreateResponse)
async def submit_draft(
    draft_id: int,
    body: DraftSubmitRequest | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """草稿正式提交 → 进入 `pending_approval`。"""
    ticket = await _get_ticket_or_404(db, draft_id)
    if not ticket.is_draft or ticket.creator_id != user.id:
        raise NotFoundError("草稿", draft_id)

    if body is not None:
        _apply_create_fields(ticket, body)

    await _validate_formal_submit(db, ticket)
    if not ticket.number:
        ticket.number = await _generate_number(db)
    ticket.is_draft = False
    ticket.state = TicketState.PENDING_APPROVAL.value
    ticket.state_version = (ticket.state_version or 1) + 1
    await db.flush()
    db.add(_write_initial_log(ticket, user, comment="提交审批"))
    await db.commit()
    return TicketCreateResponse(data=await _respond_detail(db, draft_id, user))


# ── 列表 / 导出 ────────────────────────────────────────────


@router.get("/tickets")
async def list_tickets(
    state: list[TicketState] | None = Query(None),
    priority: list[Priority] | None = Query(None),
    skill_group_id: int | None = None,
    responsible_user_id: int | None = Query(None, description="当前责任人"),
    verification_status: VerificationStatus | None = None,
    is_overdue: bool | None = None,
    keyword: str | None = None,
    date_from: str | None = Query(None, description="创建时间起始 (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="创建时间结束 (YYYY-MM-DD)"),
    sort: Literal["updated_desc", "created_desc", "planned_asc"] = "updated_desc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = _apply_filters(
        _base_query(user),
        state=state,
        priority=priority,
        skill_group_id=skill_group_id,
        responsible_user_id_filter=responsible_user_id,
        verification_status=verification_status,
        is_overdue=is_overdue,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )
    total = (
        await db.execute(select(func.count()).select_from(query.subquery()))
    ).scalar() or 0

    order = {
        "updated_desc": Ticket.updated_at.desc(),
        "created_desc": Ticket.created_at.desc(),
        "planned_asc": Ticket.planned_completion_at.asc().nulls_last(),
    }[sort]
    rows = (
        await db.execute(
            query.order_by(order).offset((page - 1) * page_size).limit(page_size)
        )
    ).scalars().all()

    return {
        "data": [_brief(t).model_dump() for t in rows],
        "pagination": {
            "page": page,
            "page_size": page_size,
            "total": total,
            "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.get("/tickets/export")
async def export_tickets(
    state: list[TicketState] | None = Query(None),
    priority: list[Priority] | None = Query(None),
    skill_group_id: int | None = None,
    responsible_user_id: int | None = Query(None),
    verification_status: VerificationStatus | None = None,
    is_overdue: bool | None = None,
    keyword: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    sort: Literal["updated_desc", "created_desc", "planned_asc"] = "updated_desc",
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """导出 POC 问题跟踪表（CSV）。数据范围与列表完全一致。"""
    query = _apply_filters(
        _base_query(user),
        state=state,
        priority=priority,
        skill_group_id=skill_group_id,
        responsible_user_id_filter=responsible_user_id,
        verification_status=verification_status,
        is_overdue=is_overdue,
        keyword=keyword,
        date_from=date_from,
        date_to=date_to,
    )
    order = {
        "updated_desc": Ticket.updated_at.desc(),
        "created_desc": Ticket.created_at.desc(),
        "planned_asc": Ticket.planned_completion_at.asc().nulls_last(),
    }[sort]
    tickets = (await db.execute(query.order_by(order))).scalars().all()

    def fmt(value: datetime | None) -> str:
        return value.strftime("%Y-%m-%d %H:%M") if value else ""

    columns = [
        ("问题编号", lambda t: t.number or ""),
        ("问题名称", lambda t: t.title or ""),
        ("提出人", lambda t: t.proposer or ""),
        ("提出部门", lambda t: t.proposer_department or ""),
        ("客户名称", lambda t: t.customer_name or ""),
        ("产品线", lambda t: t.product_line or ""),
        ("问题级别", lambda t: t.priority),
        ("问题类型", lambda t: t.problem_type or ""),
        ("发生时间", lambda t: fmt(t.occurred_at)),
        ("当前阶段", lambda t: state_label(t.state)),
        ("当前责任角色", lambda t: responsible_role(t) or ""),
        (
            "当前责任人",
            lambda t: _people(t).get(current_responsible_user_id(t) or -1, ""),
        ),
        ("分系统", lambda t: t.skill_group.name if t.skill_group else ""),
        ("计划完成时间", lambda t: fmt(t.planned_completion_at)),
        ("是否逾期", lambda t: "是" if compute_is_overdue(t) else "否"),
        ("验证状态", lambda t: t.verification_status or ""),
        ("创建人", lambda t: t.creator.name if t.creator else ""),
        ("创建时间", lambda t: fmt(t.created_at)),
        ("闭环时间", lambda t: fmt(t.closed_at)),
    ]

    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow([c[0] for c in columns])
    for t in tickets:
        writer.writerow([c[1](t) for c in columns])
    output.seek(0)

    filename = f"poc_tickets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ── 详情 / 编辑 ────────────────────────────────────────────


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ticket = await _load_detail(db, ticket_id)
    if ticket.legacy_state is not None:
        raise NotFoundError("问题", ticket_id)
    ensure_can_view(ticket, user)
    return _detail(ticket, user)


def _editable_fields(ticket: Ticket, actor: User) -> set[str]:
    """当前状态 + 当前人员允许 PATCH 的字段集合。"""
    state = ticket.state
    if state in TERMINAL_VALUES:
        return set()
    if actor.has_role(BusinessRole.ADMIN):
        return (
            set(CREATION_EDITABLE_FIELDS)
            | set(PLAN_EDITABLE_FIELDS)
            | set(ANALYSIS_EDITABLE_FIELDS)
        )
    is_presales = actor.has_role(BusinessRole.PRESALES)
    is_subsystem = actor.has_role(BusinessRole.SUBSYSTEM)
    if state == TicketState.PENDING_APPROVAL.value and is_presales and ticket.creator_id == actor.id:
        return set(CREATION_EDITABLE_FIELDS)
    if (
        state == TicketState.RETURNED.value
        and ticket.return_to_state == TicketState.PENDING_APPROVAL.value
        and is_presales
        and ticket.creator_id == actor.id
    ):
        return set(CREATION_EDITABLE_FIELDS)
    if (
        state == TicketState.PLANNING.value
        and is_subsystem
        and ticket.subsystem_owner_id == actor.id
    ):
        return set(PLAN_EDITABLE_FIELDS)
    if (
        state == TicketState.PROCESSING.value
        and is_subsystem
        and ticket.subsystem_owner_id == actor.id
    ):
        return set(ANALYSIS_EDITABLE_FIELDS)
    return set()


@router.patch("/tickets/{ticket_id}", response_model=TicketDetail)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """只修改当前节点允许编辑的业务字段，不承担任何状态流转。"""
    ticket = await _get_ticket_or_404(db, ticket_id)
    if ticket.legacy_state is not None:
        raise NotFoundError("问题", ticket_id)
    ensure_can_view(ticket, user)

    if ticket.state in TERMINAL_VALUES:
        raise HTTPException(400, detail="问题已处于终态，不能再修改")

    provided = {
        key: value
        for key, value in body.model_dump(exclude_unset=True).items()
        if value is not None
    }
    editable = _editable_fields(ticket, user)
    if not editable:
        raise ForbiddenError("当前状态下你无权修改该问题")
    illegal = sorted(set(provided) - editable)
    if illegal:
        raise HTTPException(
            400, detail="当前节点不允许修改字段：" + "、".join(illegal)
        )

    for field, value in provided.items():
        if field in ("occurred_at", "planned_completion_at"):
            value = _aware(value)
        setattr(ticket, field, value)
    ticket.updated_at = now_utc()
    await db.commit()
    return await _respond_detail(db, ticket_id, user)


# ── 统一动作入口 ───────────────────────────────────────────


@router.post("/tickets/{ticket_id}/actions", response_model=TicketDetail)
async def execute_ticket_action(
    ticket_id: int,
    body: TicketActionRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """所有状态动作的唯一入口。成功返回完整 TicketDetail。"""
    ticket = await _get_ticket_or_404(db, ticket_id, lock=True)
    if ticket.legacy_state is not None:
        raise NotFoundError("问题", ticket_id)
    ensure_can_view(ticket, user)

    await execute_action(
        db,
        ticket,
        user,
        body.action,
        payload=body.payload,
        comment=body.comment,
        expected_version=body.expected_version,
    )
    return await _respond_detail(db, ticket_id, user)


@router.get("/tickets/{ticket_id}/state-logs")
async def get_state_logs(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """流程时间线。"""
    ticket = await _load_detail(db, ticket_id)
    if ticket.legacy_state is not None:
        raise NotFoundError("问题", ticket_id)
    ensure_can_view(ticket, user)
    return {"data": [_log_out(log).model_dump() for log in (ticket.state_logs or [])]}
