"""Tickets router — CRUD, batch update, cancel, state logs, duplicate check."""

import csv
import io
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.exceptions import NotFoundError, StateTransitionError
from app.models.group import Group
from app.models.category import TicketCategory
from app.models.sla import SLAPolicy
from app.models.ticket import Ticket, TicketStateLog
from app.models.user import User
from app.schemas.ticket import (
    TicketBatchUpdate,
    TicketBrief,
    TicketCreate,
    TicketCreateResponse,
    TicketDetail,
    TicketUpdate,
    DuplicateWarning,
)
from app.services.state_machine import (
    TERMINAL_STATES,
    apply_initial_state,
    apply_transition,
    compute_allowed_actions,
    compute_article_actions,
)

router = APIRouter(tags=["tickets"])


def _ticket_to_brief(t: Ticket, terminal_ops: dict | None = None) -> TicketBrief:
    archived_by = (terminal_ops or {}).get((t.id, "archived"))
    cancelled_by = (terminal_ops or {}).get((t.id, "cancelled"))
    return TicketBrief(
        id=t.id, number=t.number, state=t.state,
        priority=t.priority, channel=t.channel, customer_type=t.customer_type,
        customer_name=t.customer_name, customer_phone=t.customer_phone, customer_phone_type=t.customer_phone_type, contact_phone=t.contact_phone,
        skill_group_id=t.skill_group_id,
        skill_group_name=t.skill_group.name if t.skill_group else None,
        handler_skill_group_id=t.handler_skill_group_id,
        handler_skill_group_name=(
            t.handler_skill_group.name if t.handler_skill_group else None
        ),
        owner_id=t.owner_id,
        owner_name=t.owner.name if t.owner else None,
        dispatcher_id=t.dispatcher_id,
        dispatcher_name=t.dispatcher.name if t.dispatcher else None,
        category_id=t.category_id,
        category_name=t.category.name if t.category else None,
        category_l1_id=t.category.parent.id if t.category and t.category.parent else t.category_id,
        category_l1_name=t.category.parent.name if t.category and t.category.parent else (t.category.name if t.category else None),
        category_l2_id=t.category.id if t.category and t.category.parent else None,
        category_l2_name=t.category.name if t.category and t.category.parent else None,
        region_name=t.region_name,
        is_duplicate=t.is_duplicate,
        is_callbacked=t.is_callbacked,
        is_draft=t.is_draft,
        sla_solution_breached=t.sla_solution_breached,
        solution_deadline=t.solution_deadline,
        urged_at=t.urged_at,
        urged_by_id=t.urged_by_id,
        urged_by_name=t.urged_by.name if t.urged_by else None,
        has_addition=t.has_addition,
        has_returned=t.has_returned,
        archived_by_id=archived_by[0] if archived_by else None,
        archived_by_name=archived_by[1] if archived_by else None,
        cancelled_by_id=cancelled_by[0] if cancelled_by else None,
        cancelled_by_name=cancelled_by[1] if cancelled_by else None,
        created_at=t.created_at, updated_at=t.updated_at,
    )


def _ticket_to_detail(
    t: Ticket,
    terminal_ops: dict | None = None,
    *,
    allowed_actions: list[dict] | None = None,
    can_reply: bool = False,
    can_addition: bool = False,
    can_remind: bool = False,
) -> TicketDetail:
    brief = _ticket_to_brief(t, terminal_ops)
    return TicketDetail(
        **brief.model_dump(),
        # V0.86 动作/能力元数据：只有 GET 详情会传入计算结果，
        # 建单等复用路径留默认值（前端跳详情页会重新 GET）
        allowed_actions=allowed_actions or [],
        is_terminal=t.state in TERMINAL_STATES,
        can_reply=can_reply,
        can_addition=can_addition,
        can_remind=can_remind,
        description=t.description,
        customer_company=t.customer_company,
        customer_level=t.customer_level,
        device_sn=t.device_sn,
        region_id=t.region_id,
        symptom=t.symptom,
        creator_id=t.creator_id,
        creator_name=t.creator.name if t.creator else None,
        first_owner_id=t.first_owner_id,
        first_owner_name=t.first_owner.name if t.first_owner else None,
        is_escalated=t.is_escalated,
        duplicate_reason=t.duplicate_reason,
        linked_ticket_id=t.linked_ticket_id,
        solved_at=t.solved_at,
        closed_at=t.closed_at,
        closed_duration_minutes=t.closed_duration_minutes,
        resolved=t.resolved,
        resolution=t.resolution,
        root_cause=t.root_cause,
        solution=t.solution,
        complaint_level=t.complaint_level,
        group_id=t.group_id,
        group_name=t.group.name if t.group else None,
        returned_to_user_id=t.returned_to_user_id,
        returned_to_user_name=t.returned_to_user.name if t.returned_to_user else None,
        callback_required=t.callback_required,
        callback_details=t.callback_details,
        archive_notes=t.archive_notes,
        satisfaction=t.satisfaction,
    )


async def _calculate_sla_deadline(
    db: AsyncSession, priority: str, skill_group_id: int | None,
    complaint_level: str | None = None,
) -> datetime | None:
    """Look up SLA policy and compute solution deadline.

    Phase 8: 当 complaint_level 设置时（如 '重大'/'重要'），按 policy.sla_resolution_multiplier
    缩短 SLA 截止时间，使重大事件获得更短的处置窗口。
    """
    # Try group+priority first, then global
    minutes = None
    for sg_id in [skill_group_id, None]:
        result = await db.execute(
            select(SLAPolicy).where(
                SLAPolicy.skill_group_id == sg_id,
                SLAPolicy.priority == priority,
            )
        )
        policy = result.scalar_one_or_none()
        if policy:
            minutes = policy.solution_minutes
            break
    if minutes is None:
        return None

    # Complaint-level multiplier (Phase 8)
    if complaint_level:
        from app.models.complaint import ComplaintEscalationPolicy
        cp = await db.execute(
            select(ComplaintEscalationPolicy).where(
                ComplaintEscalationPolicy.complaint_level == complaint_level
            )
        )
        cp_row = cp.scalar_one_or_none()
        if cp_row and cp_row.sla_resolution_multiplier:
            minutes = int(minutes * cp_row.sla_resolution_multiplier)
    return datetime.now(timezone.utc) + timedelta(minutes=minutes)


async def _is_dispatcher_anywhere(db: AsyncSession, user_id: int) -> bool:
    """检查用户是否为任意对接部门的部门对接人（用于列表可见性判断）。"""
    from app.models.group import UserSkillGroup
    result = await db.execute(
        select(func.count()).select_from(UserSkillGroup).where(
            UserSkillGroup.user_id == user_id,
            UserSkillGroup.is_dispatcher == True,
        )
    )
    return (result.scalar() or 0) > 0


async def _get_terminal_operators(
    db: AsyncSession, ticket_ids: list[int]
) -> dict[tuple[int, str], tuple[int, str]]:
    """批量取一组工单"执行 archived / cancelled 流转的人"。

    从 state_logs 取最近一次 to_state IN ('archived','cancelled') 的 operator。
    一次性 IN 查询，避免每张工单单独查（不引入 N+1）。
    不落库到 tickets 表——state_log 才是真实来源，避免漂移。

    返回 {(ticket_id, to_state): (operator_id, operator_name)}
    """
    if not ticket_ids:
        return {}
    rows = await db.execute(
        select(
            TicketStateLog.ticket_id,
            TicketStateLog.to_state,
            TicketStateLog.operator_id,
            User.name,
        )
        .join(User, User.id == TicketStateLog.operator_id)
        .where(
            TicketStateLog.ticket_id.in_(ticket_ids),
            TicketStateLog.to_state.in_(["archived", "cancelled"]),
        )
        .order_by(
            TicketStateLog.ticket_id,
            TicketStateLog.to_state,
            TicketStateLog.created_at.desc(),
        )
    )
    result: dict[tuple[int, str], tuple[int, str]] = {}
    for tid, to_state, op_id, op_name in rows.all():
        key = (tid, to_state)
        if key not in result:  # ORDER BY desc 后第一行就是最近的
            result[key] = (op_id, op_name)
    return result


# 注：状态流转权限矩阵已收口至 app.services.state_machine.check_transition_permission
# （apply_transition 的第 3 步统一执行），路由层不再自行实现权限判断。


@router.get("/tickets")
async def list_tickets(
    state: str | None = None,
    priority: str | None = None,
    skill_group_id: int | None = None,
    owner_id: int | None = None,
    creator_id: int | None = None,
    group_id: int | None = None,
    category_id: int | None = None,
    customer_type: str | None = None,
    is_duplicate: bool | None = None,
    is_callbacked: bool | None = None,
    is_overdue: bool | None = None,
    keyword: str | None = None,
    date_from: str | None = Query(None, description="创建时间起始 (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="创建时间结束 (YYYY-MM-DD)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List tickets with filters and pagination."""
    # 默认不过滤草稿
    query = select(Ticket).options(
        selectinload(Ticket.owner), selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group),
        selectinload(Ticket.category).selectinload(TicketCategory.parent), selectinload(Ticket.group),
        selectinload(Ticket.dispatcher), selectinload(Ticket.urged_by),
    ).where(Ticket.is_draft == False)
    if user.role == "handler":
        # 对接人：看派给自己的待受理工单(dispatcher_id) + 已分派给自己处理的(owner_id)
        # 处理人：只看已分派给自己的(owner_id)
        if await _is_dispatcher_anywhere(db, user.id):
            query = query.where(
                (Ticket.owner_id == user.id) | (Ticket.dispatcher_id == user.id)
            )
        else:
            query = query.where(Ticket.owner_id == user.id)
    elif user.role == "agent":
        if not user.is_group_leader:
            query = query.where(
                (Ticket.owner_id == user.id) | (Ticket.group_id == user.group_id)
            )

    if state:
        query = query.where(Ticket.state == state)
    if priority:
        query = query.where(Ticket.priority == priority)
    if skill_group_id:
        query = query.where(Ticket.skill_group_id == skill_group_id)
    if owner_id:
        query = query.where(Ticket.owner_id == owner_id)
    if creator_id:
        query = query.where(Ticket.creator_id == creator_id)
    if group_id:
        query = query.where(Ticket.group_id == group_id)
    if category_id:
        query = query.where(Ticket.category_id == category_id)
    if customer_type:
        query = query.where(Ticket.customer_type == customer_type)
    if is_duplicate is not None:
        query = query.where(Ticket.is_duplicate == is_duplicate)
    if is_callbacked is not None:
        query = query.where(Ticket.is_callbacked == is_callbacked)
    if is_overdue:
        # 进行中状态（非终态）+ SLA 超时
        query = query.where(
            Ticket.state.notin_(["archived", "cancelled"]),
            Ticket.sla_solution_breached == True,
        )
    if keyword:
        query = query.where(
            Ticket.number.ilike(f"%{keyword}%")
            | Ticket.customer_name.ilike(f"%{keyword}%")
            | Ticket.customer_phone.ilike(f"%{keyword}%")
            | Ticket.contact_phone.ilike(f"%{keyword}%")
            | Ticket.device_sn.ilike(f"%{keyword}%")
            | Ticket.customer_company.ilike(f"%{keyword}%")
            | Ticket.description.ilike(f"%{keyword}%")
            | Ticket.region_name.ilike(f"%{keyword}%")
        )

    # 创建时间区间（inclusive 端点）：date_from 00:00:00 ~ date_to 23:59:59.999999
    if date_from or date_to:
        from datetime import datetime, time
        if date_from:
            try:
                d = datetime.strptime(date_from, "%Y-%m-%d")
                query = query.where(Ticket.created_at >= datetime.combine(d, time.min))
            except ValueError:
                raise HTTPException(422, detail="date_from 格式错误，应为 YYYY-MM-DD")
        if date_to:
            try:
                d = datetime.strptime(date_to, "%Y-%m-%d")
                query = query.where(Ticket.created_at <= datetime.combine(d, time.max))
            except ValueError:
                raise HTTPException(422, detail="date_to 格式错误，应为 YYYY-MM-DD")

    # Count
    count_q = select(func.count()).select_from(query.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    # Paginate
    # 排序：催办工单全局置顶，再进行中状态的超时工单优先，再按创建时间倒序
    in_progress_breached = (
        Ticket.state.notin_(["archived", "cancelled"])
        & (Ticket.sla_solution_breached == True)
    )
    order_clauses = [
        Ticket.urged_at.desc().nulls_last(),
        in_progress_breached.desc(),
        Ticket.created_at.desc(),
    ]
    query = query.order_by(*order_clauses).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    tickets = result.scalars().all()

    terminal_ops = await _get_terminal_operators(db, [t.id for t in tickets])

    return {
        "data": [_ticket_to_brief(t, terminal_ops).model_dump() for t in tickets],
        "pagination": {
            "page": page, "page_size": page_size,
            "total": total, "total_pages": (total + page_size - 1) // page_size,
        },
    }


@router.get("/tickets/export")
async def export_tickets(
    state: str | None = None,
    priority: str | None = None,
    skill_group_id: int | None = None,
    owner_id: int | None = None,
    creator_id: int | None = None,
    group_id: int | None = None,
    category_id: int | None = None,
    customer_type: str | None = None,
    is_duplicate: bool | None = None,
    is_callbacked: bool | None = None,
    is_overdue: bool | None = None,
    keyword: str | None = None,
    date_from: str | None = Query(None, description="创建时间起始 (YYYY-MM-DD)"),
    date_to: str | None = Query(None, description="创建时间结束 (YYYY-MM-DD)"),
    columns: str | None = Query(None, description="逗号分隔的列组：base,customer,category,workflow"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """导出工单为 CSV（真实数据，按当前筛选条件）。"""
    from datetime import datetime, time
    from app.models.group import Group, SkillGroup
    from app.models.category import TicketCategory
    from app.models.user import User as UserModel

    query = (
        select(Ticket)
        .options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
            selectinload(Ticket.group),
        )
    )

    # 角色过滤（与 list_tickets 一致）
    if user.role == "handler":
        if await _is_dispatcher_anywhere(db, user.id):
            query = query.where(
                (Ticket.owner_id == user.id) | (Ticket.dispatcher_id == user.id)
            )
        else:
            query = query.where(Ticket.owner_id == user.id)
    elif user.role == "agent":
        if not user.is_group_leader:
            query = query.where((Ticket.owner_id == user.id) | (Ticket.group_id == user.group_id))

    if state:
        query = query.where(Ticket.state == state)
    if priority:
        query = query.where(Ticket.priority == priority)
    if skill_group_id:
        query = query.where(Ticket.skill_group_id == skill_group_id)
    if owner_id:
        query = query.where(Ticket.owner_id == owner_id)
    if creator_id:
        query = query.where(Ticket.creator_id == creator_id)
    if group_id:
        query = query.where(Ticket.group_id == group_id)
    if category_id:
        query = query.where(Ticket.category_id == category_id)
    if customer_type:
        query = query.where(Ticket.customer_type == customer_type)
    if is_duplicate is not None:
        query = query.where(Ticket.is_duplicate == is_duplicate)
    if is_callbacked is not None:
        query = query.where(Ticket.is_callbacked == is_callbacked)
    if is_overdue:
        query = query.where(
            Ticket.state.notin_(["archived", "cancelled"]),
            Ticket.sla_solution_breached == True,
        )
    if keyword:
        query = query.where(
            Ticket.number.ilike(f"%{keyword}%")
            | Ticket.customer_name.ilike(f"%{keyword}%")
            | Ticket.customer_phone.ilike(f"%{keyword}%")
            | Ticket.contact_phone.ilike(f"%{keyword}%")
            | Ticket.device_sn.ilike(f"%{keyword}%")
            | Ticket.customer_company.ilike(f"%{keyword}%")
            | Ticket.description.ilike(f"%{keyword}%")
            | Ticket.region_name.ilike(f"%{keyword}%")
        )

    # 创建时间区间（inclusive 端点）：date_from 00:00:00 ~ date_to 23:59:59.999999
    if date_from or date_to:
        if date_from:
            try:
                d = datetime.strptime(date_from, "%Y-%m-%d")
                query = query.where(Ticket.created_at >= datetime.combine(d, time.min))
            except ValueError:
                raise HTTPException(422, detail="date_from 格式错误，应为 YYYY-MM-DD")
        if date_to:
            try:
                d = datetime.strptime(date_to, "%Y-%m-%d")
                query = query.where(Ticket.created_at <= datetime.combine(d, time.max))
            except ValueError:
                raise HTTPException(422, detail="date_to 格式错误，应为 YYYY-MM-DD")

    query = query.order_by(Ticket.created_at.desc())
    result = await db.execute(query)
    tickets = result.scalars().all()

    # 列组：默认全部
    col_groups = set((columns or "base,customer,category,workflow").split(","))

    # 状态/优先级中文名
    state_labels = {
        "pending": "待受理", "open": "处理中", "resolved": "已处理",
        "on_hold": "暂缓处理", "returned": "退回",
        "archived": "已归档", "cancelled": "已撤销",
    }
    priority_labels = {
        "p1_urgent": "P1 特别重大事件", "p2_high": "P2 重大事件", "p3_normal": "P3 较大事件", "p4_enterprise": "P4 一般事件",
    }
    customer_type_labels = {"personal": "个人", "enterprise": "政企"}
    channel_labels = {"phone": "电话", "wechat": "微信服务号", "web": "Web", "app": "App"}
    satisfaction_labels = {"satisfied": "满意", "average": "一般", "dissatisfied": "不满意", "unrated": "未评价"}

    # 列定义：(表头, 取值函数)
    col_defs: list[tuple[str, any]] = []
    if "base" in col_groups:
        col_defs += [
            ("工单编号", lambda t: t.number),
            ("创建时间", lambda t: t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else ""),
            ("结束时间", lambda t: t.closed_at.strftime("%Y-%m-%d %H:%M") if t.closed_at else ""),
            ("关闭时长(分)", lambda t: t.closed_duration_minutes or ""),
            ("当前状态", lambda t: state_labels.get(t.state, t.state)),
            ("工单来源", lambda t: channel_labels.get(t.channel, t.channel)),
        ]
    if "customer" in col_groups:
        col_defs += [
            ("用户姓名", lambda t: t.customer_name),
            ("单位名称", lambda t: t.customer_company or ""),
            ("来电号码", lambda t: t.customer_phone),
            ("联系号码", lambda t: t.contact_phone or ""),
            ("设备编号/SN", lambda t: t.device_sn or ""),
            ("所属区域", lambda t: t.region_name or ""),
        ]
    if "category" in col_groups:
        col_defs += [
            ("一级分类", lambda t: t.category.parent.name if t.category and t.category.parent else ""),
            ("二级分类", lambda t: t.category.name if t.category else ""),
            ("问题详情", lambda t: t.symptom or ""),
            ("优先级", lambda t: priority_labels.get(t.priority, t.priority)),
        ]
    if "workflow" in col_groups:
        col_defs += [
            ("工单创建人", lambda t: t.creator.name if t.creator else ""),
            ("实际对接人", lambda t: t.dispatcher.name if t.dispatcher else ""),
            ("实际处理人", lambda t: t.owner.name if t.owner else ""),
            ("解决方案内容", lambda t: t.resolution or ""),
            ("是否回访", lambda t: "是" if t.is_callbacked else "否"),
            ("回访时间", lambda t: ""),  # 暂无独立回访时间字段
            ("客户满意度", lambda t: satisfaction_labels.get(t.satisfaction, "") if t.satisfaction else ""),
            ("归档说明", lambda t: t.archive_notes or ""),
            ("SLA是否达标", lambda t: "超时" if t.sla_solution_breached else "达标"),
        ]

    # 生成 CSV（UTF-8 BOM，Excel 友好）
    output = io.StringIO()
    output.write("﻿")
    writer = csv.writer(output)
    writer.writerow([c[0] for c in col_defs])
    for t in tickets:
        writer.writerow([c[1](t) for c in col_defs])

    output.seek(0)
    filename = f"tickets_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8")]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---- Draft endpoints (must be before /tickets/{ticket_id}) ----


@router.get("/tickets/drafts")
async def list_drafts(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get current user's draft tickets."""
    import logging
    logger = logging.getLogger(__name__)
    logger.warning(f"[DEBUG] list_drafts called by user.id={user.id}, role={user.role}")
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.owner), selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group),
            selectinload(Ticket.category).selectinload(TicketCategory.parent), selectinload(Ticket.group),
            selectinload(Ticket.dispatcher), selectinload(Ticket.urged_by),
        )
        .where(Ticket.is_draft == True, Ticket.creator_id == user.id)
        .order_by(Ticket.updated_at.desc())
    )
    tickets = result.scalars().all()
    logger.warning(f"[DEBUG] list_drafts found {len(tickets)} drafts")
    return {
        "data": [_ticket_to_brief(t) for t in tickets],
        "pagination": {"total": len(tickets)},
    }


@router.post("/tickets/drafts/{draft_id}/submit", response_model=TicketCreateResponse)
async def submit_draft(
    draft_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    """Submit a draft ticket as a formal ticket."""
    ticket = await db.get(Ticket, draft_id)
    if not ticket or not ticket.is_draft or ticket.creator_id != user.id:
        raise NotFoundError("草稿", draft_id)

    if not ticket.dispatcher_id:
        raise HTTPException(422, detail="提交前必须指定部门对接人")

    today = datetime.now().strftime("%Y%m%d")
    max_q = (
        select(func.max(Ticket.number))
        .where(Ticket.number.like(f"{today}-%"))
    )
    max_number = (await db.execute(max_q)).scalar()
    if max_number is None:
        seq = 1
    else:
        seq = int(max_number.split("-")[-1]) + 1
    ticket.number = f"{today}-{seq:04d}"

    ticket.solution_deadline = await _calculate_sla_deadline(db, ticket.priority, ticket.skill_group_id)

    ticket.is_draft = False
    await db.flush()

    # 初始状态落库（None → pending）：与建单共用执行入口
    await apply_initial_state(db, ticket, to_state="pending", operator=user)
    await db.commit()

    result = await db.execute(
        select(Ticket).options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
            selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
            selectinload(Ticket.group),
        ).where(Ticket.id == ticket.id)
    )
    ticket = result.scalar_one()
    return TicketCreateResponse(data=_ticket_to_detail(ticket))


@router.delete("/tickets/drafts/{draft_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_draft(
    draft_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Delete a draft ticket."""
    ticket = await db.get(Ticket, draft_id)
    if not ticket or not ticket.is_draft or ticket.creator_id != user.id:
        raise NotFoundError("草稿", draft_id)
    await db.delete(ticket)
    await db.commit()


@router.patch("/tickets/drafts/{draft_id}", response_model=TicketCreateResponse)
async def update_draft(
    draft_id: int,
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update a draft ticket."""
    ticket = await db.get(Ticket, draft_id)
    if not ticket or not ticket.is_draft or ticket.creator_id != user.id:
        raise NotFoundError("草稿", draft_id)

    # Update draft fields
    ticket.description = body.description
    ticket.priority = body.priority
    ticket.channel = body.channel
    ticket.customer_type = body.customer_type
    ticket.customer_name = body.customer_name
    ticket.customer_phone = body.customer_phone
    ticket.customer_phone_type = body.customer_phone_type
    ticket.contact_phone = body.contact_phone
    ticket.customer_company = body.customer_company
    ticket.customer_level = body.customer_level
    ticket.device_sn = body.device_sn
    ticket.region_id = body.region_id
    ticket.region_name = body.region_name
    ticket.category_id = body.category_id
    ticket.group_id = body.group_id or user.group_id
    ticket.skill_group_id = body.skill_group_id
    ticket.handler_skill_group_id = body.handler_skill_group_id
    ticket.dispatcher_id = body.dispatcher_id
    ticket.is_duplicate = body.is_duplicate
    ticket.duplicate_reason = body.duplicate_reason

    await db.commit()

    # Reload ticket with relationships
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
            selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group),
            selectinload(Ticket.category).selectinload(TicketCategory.parent),
            selectinload(Ticket.group), selectinload(Ticket.urged_by),
        )
        .where(Ticket.id == draft_id)
    )
    ticket = result.scalar_one()
    return TicketCreateResponse(data=_ticket_to_detail(ticket))



@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get ticket detail."""
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
            selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
            selectinload(Ticket.group), selectinload(Ticket.urged_by),
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise NotFoundError("工单", ticket_id)
    terminal_ops = await _get_terminal_operators(db, [ticket_id])
    # 后端唯一事实来源：动作/能力元数据全部由 state_machine 的真实规则生成
    allowed_actions = await compute_allowed_actions(db, ticket, user)
    article_actions = compute_article_actions(ticket, user)
    return _ticket_to_detail(ticket, terminal_ops, allowed_actions=allowed_actions, **article_actions)


@router.post("/tickets", response_model=TicketCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    """Create a new ticket."""
    warnings = None

    # Auto-match responsibility from category routing rule (Phase 5).
    # body.* wins; routing rule fills in any field the caller left blank.
    auto_match_warning: str | None = None
    if body.category_id is not None:
        from app.services.routing import resolve_rule
        rule_result = await resolve_rule(db, body.category_id)
        if rule_result.get("matched"):
            if body.skill_group_id is None and rule_result.get("dispatcher_skill_group_id"):
                body.skill_group_id = rule_result["dispatcher_skill_group_id"]
            if body.handler_skill_group_id is None:
                # Even when the rule has no professional department we still
                # leave handler_skill_group_id as the caller set it.
                body.handler_skill_group_id = rule_result.get("handler_skill_group_id")
            if body.dispatcher_id is None and rule_result.get("dispatcher_id"):
                body.dispatcher_id = rule_result["dispatcher_id"]
            # Note: owner_id is NOT auto-assigned here; the rule's default
            # owner is used by the dispatcher's "分派" step, not at creation.
            if rule_result.get("reason"):
                auto_match_warning = rule_result["reason"]
        else:
            auto_match_warning = rule_result.get("reason")

    if body.is_draft:
        # Draft: no number, no SLA, no duplicate check, relaxed validation
        ticket = Ticket(
            number=None, description=body.description,
            priority=body.priority, channel=body.channel,
            state="pending",
            customer_type=body.customer_type, customer_name=body.customer_name,
            customer_phone=body.customer_phone, customer_phone_type=body.customer_phone_type, contact_phone=body.contact_phone,
            customer_company=body.customer_company,
            customer_level=body.customer_level, device_sn=body.device_sn,
            region_id=body.region_id, region_name=body.region_name, category_id=body.category_id,
            group_id=body.group_id or user.group_id,
            skill_group_id=body.skill_group_id,
            handler_skill_group_id=body.handler_skill_group_id,
            owner_id=None,
            creator_id=user.id, first_owner_id=None,
            dispatcher_id=body.dispatcher_id,
            is_duplicate=body.is_duplicate,
            duplicate_reason=body.duplicate_reason,
            root_cause=body.root_cause,
            solution=body.solution,
            complaint_level=body.complaint_level,
            is_draft=True,
        )
    elif body.is_instant_resolve:
        # 即时办结咨询（Phase 6）：建正式工单，直接进入终态 archived。
        # 仍然走完整审计：number / SLA / state_log。
        today = datetime.now().strftime("%Y%m%d")
        max_q = (
            select(func.max(Ticket.number))
            .where(Ticket.number.like(f"{today}-%"))
        )
        max_number = (await db.execute(max_q)).scalar()
        if max_number is None:
            seq = 1
        else:
            seq = int(max_number.split("-")[-1]) + 1
        number = f"{today}-{seq:04d}"

        solution_deadline = await _calculate_sla_deadline(db, body.priority, body.skill_group_id, body.complaint_level)

        now = datetime.now(timezone.utc)
        ticket = Ticket(
            number=number, description=body.description,
            priority=body.priority, channel=body.channel,
            state="archived",
            customer_type=body.customer_type, customer_name=body.customer_name,
            customer_phone=body.customer_phone, customer_phone_type=body.customer_phone_type, contact_phone=body.contact_phone,
            customer_company=body.customer_company,
            customer_level=body.customer_level, device_sn=body.device_sn,
            region_id=body.region_id, region_name=body.region_name, category_id=body.category_id,
            group_id=body.group_id or user.group_id,
            skill_group_id=body.skill_group_id,
            handler_skill_group_id=body.handler_skill_group_id,
            owner_id=None,
            creator_id=user.id, first_owner_id=None,
            dispatcher_id=body.dispatcher_id,  # 即时办结可省略协调人
            is_duplicate=body.is_duplicate,
            duplicate_reason=body.duplicate_reason,
            root_cause=body.root_cause,
            solution=body.solution,
            complaint_level=body.complaint_level,
            solution_deadline=solution_deadline,
            resolved=True,
            resolution=body.instant_resolution or "即时办结咨询",
            solved_at=now,
            closed_at=now,
            closed_duration_minutes=0,
            callback_required=False,  # 不需要回访
            is_callbacked=True,
            is_draft=False,
        )
        db.add(ticket)
        await db.flush()
        # 一次性审计日志：None → archived（初始状态执行入口，含终态副作用）
        await apply_initial_state(
            db, ticket, to_state="archived",
            operator=user, reason="即时办结咨询", body=body,
        )
        await db.commit()

        # Reload with relationships
        result = await db.execute(
            select(Ticket).options(
                selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
                selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
                selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
                selectinload(Ticket.group),
            ).where(Ticket.id == ticket.id)
        )
        ticket = result.scalar_one()
        return TicketCreateResponse(
            data=_ticket_to_detail(ticket),
            warnings=DuplicateWarning(
                auto_match_warning="即时办结咨询：工单已直接归档，无需后续处理与回访",
            ),
        )
    else:
        # Formal ticket: generate number, SLA, duplicate check
        # Generate ticket number: YYYYMMDD-XXXX (daily counter from 0001)
        today = datetime.now().strftime("%Y%m%d")
        max_q = (
            select(func.max(Ticket.number))
            .where(Ticket.number.like(f"{today}-%"))
        )
        max_number = (await db.execute(max_q)).scalar()
        if max_number is None:
            seq = 1
        else:
            seq = int(max_number.split("-")[-1]) + 1
        number = f"{today}-{seq:04d}"

        # Calculate SLA deadline
        solution_deadline = await _calculate_sla_deadline(db, body.priority, body.skill_group_id, body.complaint_level)

        # Check duplicates
        dup_result = await db.execute(
            select(Ticket).where(
                Ticket.customer_phone == body.customer_phone,
                Ticket.state.in_(["pending", "open", "resolved", "on_hold"]),
                Ticket.is_draft == False,
            ).limit(5)
        )
        dup_tickets = dup_result.scalars().all()
        if body.category_id:
            dup_tickets = [t for t in dup_tickets if t.category_id == body.category_id]
        if dup_tickets:
            warnings = {
                "duplicate_detected": True,
                "duplicate_tickets": [
                    {"id": t.id, "number": t.number, "state": t.state, "created_at": t.created_at.isoformat()}
                    for t in dup_tickets
                ],
            }

        # Dispatcher required for formal tickets
        if not body.dispatcher_id:
            raise HTTPException(422, detail="建单时必须指定部门对接人")

        ticket = Ticket(
            number=number, description=body.description,
            priority=body.priority, channel=body.channel,
            state="pending",
            customer_type=body.customer_type, customer_name=body.customer_name,
            customer_phone=body.customer_phone, customer_phone_type=body.customer_phone_type, contact_phone=body.contact_phone,
            customer_company=body.customer_company,
            customer_level=body.customer_level, device_sn=body.device_sn,
            region_id=body.region_id, region_name=body.region_name, category_id=body.category_id,
            group_id=body.group_id or user.group_id,
            skill_group_id=body.skill_group_id,
            handler_skill_group_id=body.handler_skill_group_id,
            owner_id=None,
            creator_id=user.id, first_owner_id=None,
            dispatcher_id=body.dispatcher_id,
            is_duplicate=body.is_duplicate,
            duplicate_reason=body.duplicate_reason,
            root_cause=body.root_cause,
            solution=body.solution,
            complaint_level=body.complaint_level,
            solution_deadline=solution_deadline,
            is_draft=False,
        )

    db.add(ticket)
    await db.flush()  # to get ticket.id

    # 初始状态日志：仅正式工单记录（None → pending），草稿不写日志
    if not body.is_draft:
        await apply_initial_state(db, ticket, to_state="pending", operator=user, body=body)

    await db.refresh(ticket)

    # 显式提交，确保工单在返回前已持久化，避免前端立即跳转详情时 404
    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(Ticket).options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
            selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
            selectinload(Ticket.group),
        ).where(Ticket.id == ticket.id)
    )
    ticket = result.scalar_one()

    return TicketCreateResponse(
        data=_ticket_to_detail(ticket),
        warnings=DuplicateWarning(
            duplicate_detected=bool(warnings and warnings.get("duplicate_detected")),
            duplicate_tickets=(warnings or {}).get("duplicate_tickets", []),
            auto_match_warning=auto_match_warning,
        ) if (warnings or auto_match_warning) else None,
    )


@router.patch("/tickets/{ticket_id}", response_model=TicketDetail)
async def update_ticket(
    ticket_id: int,
    body: TicketUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Update ticket fields (state, priority, owner, etc.)."""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise NotFoundError("工单", ticket_id)

    # State transition — 唯一执行入口：校验/权限/reason/副作用/Flow Log 全部收口
    # （业务约束改写、resolved→on_hold 兜底等见 app.services.state_machine.apply_transition）
    if body.state is not None and body.state != ticket.state:
        await apply_transition(
            db, ticket,
            to_state=body.state,
            operator=user,
            reason=body.reason,
            owner_id=body.owner_id,
            dispatcher_id=body.dispatcher_id,
            hold_until=body.hold_until,
        )
    if body.archive_notes is not None:
        ticket.archive_notes = body.archive_notes
    if body.is_callbacked is not None:
        ticket.is_callbacked = body.is_callbacked
        # 未回访时清空满意度；避免历史脏数据
        if body.is_callbacked is False:
            ticket.satisfaction = None
    if body.callback_required is not None:
        ticket.callback_required = body.callback_required
        if body.callback_required is False:
            # 无需回访：强制已回访标记为否并清空满意度
            ticket.is_callbacked = False
            ticket.satisfaction = None
    if body.satisfaction is not None:
        # 校验：satisfaction 仅在 is_callbacked=true 时有意义
        allowed = {"satisfied", "average", "dissatisfied", "unrated"}
        if body.satisfaction not in allowed:
            raise HTTPException(422, detail=f"satisfaction 取值必须是 {sorted(allowed)} 之一")
        if ticket.is_callbacked is False:
            raise HTTPException(422, detail="未回访工单不能设置满意度")
        ticket.satisfaction = body.satisfaction
    if body.priority is not None:
        ticket.priority = body.priority
        # Recalculate SLA deadline (creation → resolved)
        if ticket.solved_at is None:
            ticket.solution_deadline = await _calculate_sla_deadline(db, body.priority, ticket.skill_group_id, ticket.complaint_level)

    if body.owner_id is not None:
        ticket.owner_id = body.owner_id
    if body.group_id is not None:
        ticket.group_id = body.group_id
    if body.skill_group_id is not None:
        ticket.skill_group_id = body.skill_group_id
    if body.handler_skill_group_id is not None:
        ticket.handler_skill_group_id = body.handler_skill_group_id
    if body.dispatcher_id is not None:
        ticket.dispatcher_id = body.dispatcher_id
    # Phase 7: structured processing
    if body.root_cause is not None:
        ticket.root_cause = body.root_cause
    if body.solution is not None:
        ticket.solution = body.solution
    # Phase 8: complaint routing
    if body.complaint_level is not None:
        ticket.complaint_level = body.complaint_level

    await db.flush()

    # Reload with relationships
    result = await db.execute(
        select(Ticket).options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
            selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
            selectinload(Ticket.group),
        ).where(Ticket.id == ticket.id)
    )
    ticket = result.scalar_one()
    return _ticket_to_detail(ticket)


@router.post("/tickets/batch-update")
async def batch_update_tickets(
    body: TicketBatchUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    """Batch update tickets.

    状态流转与单条 PATCH 同源：统一走 apply_transition（权限 / reason / 状态副作用 /
    Flow Log 全在执行入口内完成）。语义：
      - 非法流转：跳过该工单（保留批量接口原有的容错语义）
      - 无权限 / 缺 reason：整批拒绝（403 / 400），事务回滚，不做部分提交
    """
    result = await db.execute(
        select(Ticket).where(Ticket.id.in_(body.ticket_ids))
    )
    tickets = result.scalars().all()
    updated = 0
    for ticket in tickets:
        # 先应用非 state 字段（owner/dsp/group/skill_group/priority），这样流转快照
        # 写入时 ticket 已携带新值
        if body.updates.priority is not None:
            ticket.priority = body.updates.priority
        if body.updates.group_id is not None:
            ticket.group_id = body.updates.group_id
        if body.updates.skill_group_id is not None:
            ticket.skill_group_id = body.updates.skill_group_id
        if body.updates.handler_skill_group_id is not None:
            ticket.handler_skill_group_id = body.updates.handler_skill_group_id
        if body.updates.owner_id is not None:
            ticket.owner_id = body.updates.owner_id
        if body.updates.dispatcher_id is not None:
            ticket.dispatcher_id = body.updates.dispatcher_id
        if body.updates.state is not None and body.updates.state != ticket.state:
            try:
                await apply_transition(
                    db, ticket,
                    to_state=body.updates.state,
                    operator=user,
                    reason=body.updates.reason,
                    owner_id=body.updates.owner_id,
                    dispatcher_id=body.updates.dispatcher_id,
                    hold_until=body.updates.hold_until,
                )
            except StateTransitionError:
                continue  # skip invalid transitions
        updated += 1
    await db.flush()
    return {"data": {"updated": updated}}


@router.get("/tickets/{ticket_id}/state-logs")
async def get_state_logs(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Get ticket state transition logs."""
    result = await db.execute(
        select(TicketStateLog)
        .where(TicketStateLog.ticket_id == ticket_id)
        .order_by(TicketStateLog.created_at.asc())
    )
    logs = result.scalars().all()
    if not logs:
        return {"data": []}

    # 一次拉出所有相关 user，避免 N+1
    user_ids: set[int] = set()
    for log in logs:
        if log.operator_id:
            user_ids.add(log.operator_id)
        if log.creator_id_snapshot:
            user_ids.add(log.creator_id_snapshot)
        if log.dispatcher_id_snapshot:
            user_ids.add(log.dispatcher_id_snapshot)
        if log.owner_id_snapshot:
            user_ids.add(log.owner_id_snapshot)

    user_map: dict[int, str] = {}
    if user_ids:
        ures = await db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
        user_map = {row[0]: row[1] for row in ures.all()}

    def _name(uid):
        return user_map.get(uid) if uid else None

    data = []
    for log in logs:
        data.append({
            "id": log.id, "from_state": log.from_state, "to_state": log.to_state,
            "operator_id": log.operator_id,
            "operator_name": _name(log.operator_id),
            # 人员快照：写入 state_log 那一刻工单上的创建者/对接人/处理人
            "creator_id_snapshot": log.creator_id_snapshot,
            "creator_name_snapshot": _name(log.creator_id_snapshot),
            "dispatcher_id_snapshot": log.dispatcher_id_snapshot,
            "dispatcher_name_snapshot": _name(log.dispatcher_id_snapshot),
            "owner_id_snapshot": log.owner_id_snapshot,
            "owner_name_snapshot": _name(log.owner_id_snapshot),
            "reason": log.reason, "duration_minutes": log.duration_minutes,
            # 动作类型：create/dispatch/hold/resume/resolve/reopen/return/
            # resubmit/archive/cancel/instant_resolve（历史日志为 null）
            "action_type": log.action_type,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return {"data": data}
