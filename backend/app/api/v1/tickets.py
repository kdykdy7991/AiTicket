"""Tickets router — CRUD, batch update, cancel, state logs, duplicate check."""

import csv
import io
import json
import re
import shutil
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import NamedTuple, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.exceptions import NotFoundError, StateTransitionError
from app.models.group import Group
from app.models.group import SkillGroup, UserSkillGroup
from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.services.sla import start_round, replace_running_deadline, root_category
from app.models.ticket import Article, ArticleAttachment, Ticket, TicketStateLog
from app.models.node_form import FormDefinition, TicketNodeSubmission
from app.models.user import User
from app.schemas.ticket import (
    TicketBatchUpdate,
    TicketBrief,
    TicketCreate,
    TicketCreateResponse,
    TicketDetail,
    TicketRefine,
    TicketUpdate,
    DuplicateWarning,
)
from app.services.category_utils import (
    CategoryLineage,
    ResponsibilitySlots,
    build_lineage_index,
    build_responsibility_index,
    create_selectable_categories,
    is_valid_ticket_category,
    INSTANT_CONSULT_CATEGORY_ID,
)
from app.services.state_machine import (
    TERMINAL_STATES,
    action_for,
    apply_initial_state,
    apply_refine,
    apply_transition,
    compute_allowed_actions,
    compute_article_actions,
    refine_capability,
    check_transition_permission,
    is_dispatcher,
    transition_permission_error,
    transition_precondition_error,
)
from app.services.callback_policy import resolve_callback_required
from app.services.node_context import NodeContext, NodeContextConflict, resolve_node_context
from app.services.node_form import resolve_form, present_form, validate_submission

router = APIRouter(tags=["tickets"])


async def _sales_group_for_owner(db: AsyncSession, owner_id: int | None) -> SkillGroup:
    """Validate the directly assigned sales handler for a formal opportunity."""
    group = (await db.execute(select(SkillGroup).where(SkillGroup.name == "销售"))).scalar_one_or_none()
    if group is None or owner_id is None:
        raise HTTPException(422, detail="请选择销售部门人员")
    now = datetime.now(timezone.utc)
    person = (await db.execute(select(User).join(
        UserSkillGroup, UserSkillGroup.user_id == User.id,
    ).where(
        User.id == owner_id, User.is_active.is_(True),
        UserSkillGroup.skill_group_id == group.id,
        or_(UserSkillGroup.effective_from.is_(None), UserSkillGroup.effective_from <= now),
        or_(UserSkillGroup.effective_to.is_(None), UserSkillGroup.effective_to >= now),
    ))).scalar_one_or_none()
    if person is None:
        raise HTTPException(422, detail="所选人员不是当前有效的销售部门成员")
    return group


class CategoryIndexes(NamedTuple):
    """分类派生的两个索引，一次请求内共用（分类/分派链各只查一次）。"""

    lineage: dict[int, CategoryLineage]
    responsibility: dict[int, ResponsibilitySlots]


async def get_category_indexes(
    db: AsyncSession = Depends(get_db),
) -> CategoryIndexes:
    """分类血缘 + 责任槽位索引（请求级缓存）。"""
    return CategoryIndexes(
        lineage=await build_lineage_index(db),
        responsibility=await build_responsibility_index(db),
    )


def _dept_of(user: User | None, prefer_skill_group_id: int | None) -> str | None:
    """人员的所属部门名（优先工单当前责任部门，其次其任一所属部门）。

    User.skill_groups 是 lazy="selectin"，此处同步读取安全。
    一个人可能属于多个部门（如既在网运部又在业务支撑组），与工单责任部门
    匹配的那个才是本单语境下有意义的那个；都不匹配时回退首个，让跨部门
    错配在界面上可见（而不是悄悄显示一个不相干的部门）。
    """
    if user is None:
        return None
    names = [sg.name for sg in (user.skill_groups or []) if sg.name]
    if not names:
        return None
    if prefer_skill_group_id:
        for sg in user.skill_groups or []:
            if sg.id == prefer_skill_group_id:
                return sg.name
    return names[0]


def _resolve_lineage(
    t: Ticket,
    lineage: dict[int, CategoryLineage] | None,
) -> tuple[TicketCategory | None, TicketCategory | None, TicketCategory | None, str | None]:
    """从血缘索引解析 (叶子, L1, L2, 完整路径)。

    分类树是任意深度的，L1 必须沿 parent 链走到根——早期实现只取一层 parent，
    在 V2 四层树上会把二级节点（业务保障）误当作一级。索引缺失时退化为
    「自身即 L1」，保证单条/旧路径不报错。
    """
    if t.category is None:
        return None, None, None, None
    lin = lineage.get(t.category_id) if lineage and t.category_id else None
    if lin is None or not lin.path:
        return t.category, t.category, None, t.category.name
    leaf = lin.path[-1]
    path = " / ".join(c.name for c in lin.path)
    return leaf, lin.l1, lin.l2, path


def _ticket_to_brief(
    t: Ticket,
    terminal_ops: dict | None = None,
    lineage: dict[int, CategoryLineage] | None = None,
    responsibility: dict[int, ResponsibilitySlots] | None = None,
) -> TicketBrief:
    archived_by = (terminal_ops or {}).get((t.id, "archived"))
    cancelled_by = (terminal_ops or {}).get((t.id, "cancelled"))
    cat_leaf, cat_l1, cat_l2, cat_path = _resolve_lineage(t, lineage)
    slots = responsibility.get(t.category_id) if responsibility and t.category_id else None
    return TicketBrief(
        id=t.id, number=t.number, state=t.state,
        priority=t.priority, channel=t.channel, customer_type=t.customer_type,
        customer_name=t.customer_name, customer_phone=t.customer_phone, customer_phone_type=t.customer_phone_type, contact_phone=t.contact_phone,
        is_opportunity=t.is_opportunity,
        skill_group_id=t.skill_group_id,
        skill_group_name=t.skill_group.name if t.skill_group else None,
        handler_skill_group_id=t.handler_skill_group_id,
        handler_skill_group_name=(
            t.handler_skill_group.name if t.handler_skill_group else None
        ),
        owner_id=t.owner_id,
        owner_name=t.owner.name if t.owner else None,
        owner_department=_dept_of(t.owner, t.skill_group_id),
        dispatcher_id=t.dispatcher_id,
        dispatcher_name=t.dispatcher.name if t.dispatcher else None,
        dispatcher_department=_dept_of(t.dispatcher, t.skill_group_id),
        category_id=t.category_id,
        category_name=cat_leaf.name if cat_leaf else None,
        category_l1_id=cat_l1.id if cat_l1 else t.category_id,
        category_l1_name=cat_l1.name if cat_l1 else (cat_leaf.name if cat_leaf else None),
        category_l2_id=cat_l2.id if cat_l2 else None,
        category_l2_name=cat_l2.name if cat_l2 else None,
        category_path=cat_path,
        judgement_departments=list(slots.judgement_departments) if slots else [],
        transit_departments=list(slots.transit_departments) if slots else [],
        handling_department=slots.handling_department if slots else None,
        region_name=t.region_name,
        is_duplicate=t.is_duplicate,
        is_callbacked=t.is_callbacked,
        is_draft=t.is_draft,
        sla_solution_breached=t.sla_solution_breached,
        solution_deadline=t.solution_deadline,
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
    lineage: dict[int, CategoryLineage] | None = None,
    responsibility: dict[int, ResponsibilitySlots] | None = None,
    allowed_actions: list[dict] | None = None,
    can_reply: bool = False,
    can_addition: bool = False,
    can_refine: bool = False,
    refine_options: list[dict] | None = None,
    refine_denied_reason: str | None = None,
    node_context: dict | None = None,
    current_form: dict | None = None,
) -> TicketDetail:
    brief = _ticket_to_brief(t, terminal_ops, lineage, responsibility)
    return TicketDetail(
        **brief.model_dump(),
        # V0.86 动作/能力元数据：只有 GET 详情会传入计算结果，
        # 建单等复用路径留默认值（前端跳详情页会重新 GET）
        allowed_actions=allowed_actions or [],
        is_terminal=t.state in TERMINAL_STATES,
        can_reply=can_reply,
        can_addition=can_addition,
        can_refine=can_refine,
        refine_options=refine_options or [],
        refine_denied_reason=refine_denied_reason,
        node_context=node_context,
        current_form=current_form,
        sla_rounds=[{
            "sequence": round_.sequence, "started_at": round_.started_at,
            "deadline_at": round_.deadline_at, "ended_at": round_.ended_at,
            "status": round_.status, "breached": round_.breached,
        } for round_ in t.sla_rounds],
        description=t.description,
        customer_company=t.customer_company,
        industry=t.industry,
        customer_email=t.customer_email,
        satellite_number=t.satellite_number,
        expected_result=t.expected_result,
        fault_occurred_at=t.fault_occurred_at,
        fault_recurrence=t.fault_recurrence,
        fault_location=t.fault_location,
        is_batch_fault=t.is_batch_fault,
        customer_level=t.customer_level,
        device_sn=t.device_sn,
        region_id=t.region_id,
        symptom=t.symptom,
        creator_id=t.creator_id,
        creator_name=t.creator.name if t.creator else None,
        creator_username=t.creator.username if t.creator else None,
        creator_group_name=t.creator.group.name if t.creator and t.creator.group else None,
        first_owner_id=t.first_owner_id,
        first_owner_name=t.first_owner.name if t.first_owner else None,
        is_escalated=t.is_escalated,
        duplicate_reason=t.duplicate_reason,
        linked_ticket_id=t.linked_ticket_id,
        solved_at=t.solved_at,
        hold_until=t.hold_until,
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
        customer_satisfaction_score=t.customer_satisfaction_score,
        unsatisfied_reason=t.unsatisfied_reason,
        closure_result=t.closure_result,
        customer_recognized=t.customer_recognized,
        dispatch_chain_steps=t.dispatch_chain_steps,
        dispatch_step_index=t.dispatch_step_index,
    )


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
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(get_current_user),
):
    """List tickets with filters and pagination."""
    # 默认不过滤草稿
    query = select(Ticket).options(
        selectinload(Ticket.owner), selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group),
        selectinload(Ticket.category).selectinload(TicketCategory.parent), selectinload(Ticket.group),
        selectinload(Ticket.dispatcher),
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
    # 排序：进行中且 SLA 超时的工单优先，再按创建时间倒序
    in_progress_breached = (
        Ticket.state.notin_(["archived", "cancelled"])
        & (Ticket.sla_solution_breached == True)
    )
    order_clauses = [
        in_progress_breached.desc(),
        Ticket.created_at.desc(),
    ]
    query = query.order_by(*order_clauses).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    tickets = result.scalars().all()

    terminal_ops = await _get_terminal_operators(db, [t.id for t in tickets])

    return {
        "data": [_ticket_to_brief(t, terminal_ops, cat_idx.lineage, cat_idx.responsibility).model_dump() for t in tickets],
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
    columns: str | None = Query(None, description="逗号分隔的字段键，顺序即导出列顺序"),
    db: AsyncSession = Depends(get_db),
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(get_current_user),
):
    """导出工单为 CSV（真实数据，按当前筛选条件）。"""
    from datetime import datetime, time
    query = (
        select(Ticket).where(Ticket.is_draft.is_(False))
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

    in_progress_breached = (
        Ticket.state.notin_(["archived", "cancelled"])
        & (Ticket.sla_solution_breached.is_(True))
    )
    query = query.order_by(
        in_progress_breached.desc(),
        Ticket.created_at.desc(),
    )
    result = await db.execute(query)
    tickets = result.scalars().all()

    # 逐列选择，字段键、顺序和用户在弹窗中的选择保持一致。
    state_labels = {
        "pending": "待受理", "open": "处理中", "resolved": "已处理",
        "on_hold": "暂缓处理", "returned": "退回",
        "archived": "已归档", "cancelled": "已撤销",
    }
    priority_labels = {
        "p1_urgent": "P1 特别重大事件", "p2_high": "P2 重大事件", "p3_normal": "P3 较大事件", "p4_enterprise": "P4 一般事件",
    }
    channel_labels = {"phone": "语音", "wechat": "微信服务号/公众号", "internal": "内部转办", "web": "在线客服", "email": "邮件", "app": "App"}
    satisfaction_labels = {"satisfied": "满意", "average": "一般", "dissatisfied": "不满意", "unrated": "未评价"}
    local_tz = timezone(timedelta(hours=8))

    def _local_time(value: datetime | None) -> str:
        return value.astimezone(local_tz).strftime("%Y-%m-%d %H:%M") if value else ""

    lineage_cache: dict[int, tuple] = {}

    def _lineage(ticket: Ticket) -> tuple:
        if ticket.id not in lineage_cache:
            lineage_cache[ticket.id] = _resolve_lineage(ticket, cat_idx.lineage)
        return lineage_cache[ticket.id]

    column_specs: dict[str, tuple[str, Any]] = {
        "number": ("工单号", lambda t: t.number or ""),
        "created_at": ("受理时间", lambda t: _local_time(t.created_at)),
        "closed_at": ("结束时间", lambda t: _local_time(t.closed_at)),
        "close_duration": ("关闭时长（分钟）", lambda t: t.closed_duration_minutes if t.closed_duration_minutes is not None else ""),
        "state": ("当前状态", lambda t: state_labels.get(t.state, t.state)),
        "channel": ("受理渠道", lambda t: channel_labels.get(t.channel, t.channel)),
        "customer_name": ("客户名称", lambda t: t.customer_name or ""),
        "customer_company": ("单位全称", lambda t: t.customer_company or ""),
        "industry": ("行业", lambda t: t.industry or ""),
        "customer_phone": ("来电号码", lambda t: t.customer_phone or ""),
        "contact_phone": ("联系号码", lambda t: t.contact_phone or ""),
        "device_sn": ("设备 SN", lambda t: t.device_sn or ""),
        "region_name": ("区域", lambda t: t.region_name or ""),
        "is_opportunity": ("是否为线索工单", lambda t: "是" if t.is_opportunity else "否" if t.is_opportunity is False else ""),
        "satellite_number": ("卫星物联网码号", lambda t: t.satellite_number or ""),
        "category_l1": ("一级分类", lambda t: _lineage(t)[1].name if _lineage(t)[1] else ""),
        "category_l2": ("二级分类", lambda t: _lineage(t)[2].name if _lineage(t)[2] else ""),
        "category_path": ("分类路径", lambda t: _lineage(t)[3] or ""),
        "description": ("客户问题详情", lambda t: t.description or ""),
        "priority": ("优先级", lambda t: priority_labels.get(t.priority, t.priority)),
        "fault_occurred_at": ("故障发生时间", lambda t: _local_time(t.fault_occurred_at)),
        "fault_recurrence": ("故障复现规律", lambda t: t.fault_recurrence or ""),
        "fault_location": ("故障发生地理位置", lambda t: t.fault_location or ""),
        "is_batch_fault": ("是否批量故障", lambda t: "是" if t.is_batch_fault else "否" if t.is_batch_fault is False else ""),
        "creator_name": ("受理人", lambda t: t.creator.name if t.creator else ""),
        "creator_group": ("受理班组", lambda t: t.group.name if t.group else ""),
        "dispatcher_name": ("对接人", lambda t: t.dispatcher.name if t.dispatcher else ""),
        "owner_name": ("当前处理人", lambda t: t.owner.name if t.owner else ""),
        "resolution": ("处理结果", lambda t: t.resolution or ""),
        "is_callbacked": ("是否已回访", lambda t: "是" if t.is_callbacked else "否"),
        "callback_details": ("回访记录", lambda t: t.callback_details or ""),
        "customer_recognized": ("客户是否认可", lambda t: "认可" if t.customer_recognized else "不认可" if t.customer_recognized is False else ""),
        "customer_satisfaction_score": ("客户满意度评分", lambda t: t.customer_satisfaction_score if t.customer_satisfaction_score is not None else ""),
        "satisfaction": ("客户满意度", lambda t: satisfaction_labels.get(t.satisfaction, "")),
        "archive_notes": ("归档说明", lambda t: t.archive_notes or ""),
        "sla_breached": ("SLA 解决时限", lambda t: "超时" if t.sla_solution_breached else "未超时"),
    }
    selected_keys = columns.split(",") if columns is not None else list(column_specs)
    if not selected_keys or any(key not in column_specs for key in selected_keys):
        raise HTTPException(422, detail="导出字段无效")
    col_defs = [column_specs[key] for key in selected_keys]

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
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
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
            selectinload(Ticket.dispatcher),
        )
        .where(Ticket.is_draft == True, Ticket.creator_id == user.id)
        .order_by(Ticket.updated_at.desc())
    )
    tickets = result.scalars().all()
    logger.warning(f"[DEBUG] list_drafts found {len(tickets)} drafts")
    return {
        "data": [_ticket_to_brief(t, None, cat_idx.lineage, cat_idx.responsibility) for t in tickets],
        "pagination": {"total": len(tickets)},
    }


@router.post("/tickets/drafts/{draft_id}/submit", response_model=TicketCreateResponse)
async def submit_draft(
    draft_id: int,
    db: AsyncSession = Depends(get_db),
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(require_role("admin", "agent")),
):
    """Submit a draft ticket as a formal ticket."""
    ticket = await db.get(Ticket, draft_id)
    if not ticket or not ticket.is_draft or ticket.creator_id != user.id:
        raise NotFoundError("草稿", draft_id)

    if ticket.category_id is not None and not await is_valid_ticket_category(db, ticket.category_id):
        raise HTTPException(422, detail="当前问题分类还需继续细化，或不能由客服建单选择")

    is_instant_consult = ticket.category_id == INSTANT_CONSULT_CATEGORY_ID
    if is_instant_consult:
        if ticket.is_opportunity:
            raise HTTPException(422, detail="即时办结咨询不能作为线索工单")
        if not ticket.customer_phone.strip() or not ticket.description.strip() or not (ticket.resolution or "").strip():
            raise HTTPException(422, detail="请填写来电号码、咨询内容和即时答复内容")
        ticket.priority = "p4_enterprise"
        ticket.owner_id = None
        ticket.dispatcher_id = None
        ticket.skill_group_id = None
        ticket.handler_skill_group_id = None
        ticket.dispatch_chain_steps = None
        ticket.dispatch_step_index = None

    if not is_instant_consult and (ticket.is_opportunity or ticket.category_id == 2204):
        sales_group = await _sales_group_for_owner(db, ticket.owner_id)
        ticket.skill_group_id = sales_group.id
        ticket.handler_skill_group_id = sales_group.id
        ticket.dispatcher_id = None
        if ticket.category_id == 2204:
            ticket.dispatch_chain_steps = [
                {"order": 1, "department_code": "销售"},
                {"order": 2, "department_code": "财务"},
            ]
            ticket.dispatch_step_index = 0
    elif not is_instant_consult and not ticket.dispatcher_id:
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

    ticket.is_draft = False
    await db.flush()
    await start_round(db, ticket, is_instant=is_instant_consult)

    # 初始状态落库（None → pending）：与建单共用执行入口
    await apply_initial_state(db, ticket, to_state="archived" if is_instant_consult else "pending", operator=user)
    if is_instant_consult:
        ticket.resolved = True
        ticket.solved_at = ticket.closed_at
        ticket.first_response_at = ticket.closed_at
    elif ticket.is_opportunity or ticket.category_id == 2204:
        await apply_transition(db, ticket, to_state="open", operator=user,
                               owner_id=ticket.owner_id, allow_sales_intake=True)
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
    return TicketCreateResponse(data=_ticket_to_detail(ticket, lineage=cat_idx.lineage, responsibility=cat_idx.responsibility))


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
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(get_current_user),
):
    """Update a draft ticket."""
    ticket = await db.get(Ticket, draft_id)
    if not ticket or not ticket.is_draft or ticket.creator_id != user.id:
        raise NotFoundError("草稿", draft_id)

    if body.category_id is not None and not await is_valid_ticket_category(db, body.category_id):
        raise HTTPException(422, detail="当前问题分类还需继续细化，或不能由客服建单选择")
    if body.category_id == INSTANT_CONSULT_CATEGORY_ID and body.is_opportunity:
        raise HTTPException(422, detail="即时办结咨询不能作为线索工单")

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
    ticket.industry = body.industry
    ticket.customer_email = body.customer_email
    ticket.resolution = ((body.instant_resolution or "").strip() or None
                         if body.category_id == INSTANT_CONSULT_CATEGORY_ID else None)
    ticket.satellite_number = body.satellite_number
    ticket.is_opportunity = body.is_opportunity
    ticket.expected_result = body.expected_result
    ticket.fault_occurred_at = body.fault_occurred_at
    ticket.fault_recurrence = body.fault_recurrence
    ticket.fault_location = body.fault_location
    ticket.is_batch_fault = body.is_batch_fault
    ticket.customer_level = body.customer_level
    ticket.device_sn = body.device_sn
    ticket.region_id = body.region_id
    ticket.region_name = body.region_name
    ticket.category_id = body.category_id
    ticket.callback_required = await resolve_callback_required(db, body.category_id)
    ticket.group_id = body.group_id or user.group_id
    ticket.skill_group_id = body.skill_group_id
    ticket.handler_skill_group_id = body.handler_skill_group_id
    ticket.dispatcher_id = None if body.is_opportunity or body.category_id == 2204 else body.dispatcher_id
    ticket.owner_id = body.sales_owner_id if body.is_opportunity or body.category_id == 2204 else None
    if body.category_id == 2204 and not body.is_opportunity:
        ticket.dispatch_chain_steps = [
            {"order": 1, "department_code": "销售"},
            {"order": 2, "department_code": "财务"},
        ]
        ticket.dispatch_step_index = 0
    else:
        ticket.dispatch_chain_steps = None
        ticket.dispatch_step_index = None
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
            selectinload(Ticket.group),
        )
        .where(Ticket.id == draft_id)
    )
    ticket = result.scalar_one()
    return TicketCreateResponse(data=_ticket_to_detail(ticket, lineage=cat_idx.lineage, responsibility=cat_idx.responsibility))



def closure_condition_context(ticket: Ticket) -> dict:
    """闭环表单的只读条件上下文：回访要求由更早的流程确定，Closure 不改写它。

    表单据此决定「是否已完成回访」等字段是否出现；客服提交的值无法伪造它，
    因为它不来自请求体。
    """
    return {"callback_required": ticket.callback_required}


async def _compose_node_form(
    db: AsyncSession,
    ticket: Ticket,
    context: NodeContext,
    user: User,
    allowed_actions: list[dict],
    article_actions: dict,
    refine: dict,
    node_context: dict,
) -> dict | None:
    """当前节点表单，以及由此产生的动作/能力位调整（详情与变更后响应共用）。

    closure 只对「此刻确实能归档的人」下发表单：满意度为不满意时归档前置不成立，
    此时仍走既有回访记录入口，闭环表单不得用来绕过不满意限制。
    """
    node_type = context.node_type
    if node_type == "triage":
        article_actions["can_reply"] = False
    if node_type == "closure":
        # 已产生不满意事实时只走「退回重开」，不下发闭环表单：否则可以原地改写评价，
        # 绕过「不满意必须重新处理」的既有约束。
        if ticket.satisfaction == "dissatisfied":
            return None
        # 权限仍按归档动作判定（客服团队 / admin），但不再要求归档前置已满足：
        # 「要求回访但未回访」的工单需要先通过本表单记录回访事实。
        if await transition_permission_error(db, ticket, "archived", user) is not None:
            return None
        form = await resolve_form(db, context)
        # 回访要求是只读事实：随表单一起下发，供界面展示且驱动字段可见性。
        return (await present_form(db, form, ticket, values=closure_condition_context(ticket))
                if form else None)
    if node_type not in ("triage", "processing", "phone_feedback", "sales_opportunity"):
        return None
    if not (refine["can_refine"] or article_actions["can_reply"]):
        return None
    form = await resolve_form(db, context)
    if not form:
        return None
    if node_type in ("processing", "phone_feedback", "sales_opportunity") and article_actions["can_reply"]:
        article_actions["can_reply"] = False
        node_context["allowed_actions"] = [
            a for a in node_context["allowed_actions"] if a["action"] != "reply"
        ]
    return await present_form(db, form, ticket)


@router.get("/tickets/{ticket_id}", response_model=TicketDetail)
async def get_ticket(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(get_current_user),
):
    """Get ticket detail."""
    result = await db.execute(
        select(Ticket)
        .options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
            selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
            selectinload(Ticket.group),
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise NotFoundError("工单", ticket_id)
    if ticket.is_draft and ticket.creator_id != user.id:
        raise NotFoundError("草稿", ticket_id)
    terminal_ops = await _get_terminal_operators(db, [ticket_id])
    if user.role == "observer":
        return _ticket_to_detail(
            ticket, terminal_ops,
            lineage=cat_idx.lineage, responsibility=cat_idx.responsibility,
            allowed_actions=[], can_reply=False, can_addition=False,
            can_refine=False, node_context=None, current_form=None,
        )
    # 后端唯一事实来源：动作/能力元数据全部由 state_machine 的真实规则生成
    try:
        allowed_actions = await compute_allowed_actions(db, ticket, user)
        article_actions = compute_article_actions(ticket, user)
        refine = await refine_capability(db, ticket, user)
        context = await resolve_node_context(
            db, ticket, user, state_actions=allowed_actions,
            article_actions=article_actions, refine=refine,
        )
    except NodeContextConflict as exc:
        raise HTTPException(409, detail={"code": "node_context_conflict", "message": str(exc)}) from exc
    node_context = asdict(context)
    current_form = await _compose_node_form(
        db, ticket, context, user, allowed_actions, article_actions, refine, node_context,
    )
    return _ticket_to_detail(
        ticket, terminal_ops,
        lineage=cat_idx.lineage,
        responsibility=cat_idx.responsibility,
        allowed_actions=allowed_actions,
        **article_actions,
        can_refine=refine["can_refine"],
        refine_options=refine["refine_options"],
        refine_denied_reason=refine["refine_denied_reason"],
        node_context=node_context,
        current_form=current_form,
    )


async def _detail_after_mutation(
    db: AsyncSession,
    ticket_id: int,
    user: User,
    lineage: dict[int, CategoryLineage] | None = None,
    responsibility: dict[int, ResponsibilitySlots] | None = None,
) -> TicketCreateResponse:
    """域动作（分诊/转派）commit 后重建详情响应。

    expire_on_commit=False 时 session 里的 ticket 持有突变前的关系对象，
    必须 populate_existing 才能让 selectinload 覆盖——否则序列化触发
    同步懒加载（MissingGreenlet 500）。
    """
    result = await db.execute(
        select(Ticket).options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
            selectinload(Ticket.skill_group), selectinload(Ticket.handler_skill_group),
            selectinload(Ticket.category).selectinload(TicketCategory.parent),
            selectinload(Ticket.group),
        ).where(Ticket.id == ticket_id).execution_options(populate_existing=True)
    )
    ticket = result.scalar_one()
    terminal_ops = await _get_terminal_operators(db, [ticket.id])
    try:
        allowed_actions = await compute_allowed_actions(db, ticket, user)
        article_actions = compute_article_actions(ticket, user)
        refine = await refine_capability(db, ticket, user)
        context = await resolve_node_context(
            db, ticket, user, state_actions=allowed_actions,
            article_actions=article_actions, refine=refine,
        )
    except NodeContextConflict as exc:
        raise HTTPException(409, detail={"code": "node_context_conflict", "message": str(exc)}) from exc
    node_context = asdict(context)
    current_form = await _compose_node_form(
        db, ticket, context, user, allowed_actions, article_actions, refine, node_context,
    )
    return TicketCreateResponse(
        data=_ticket_to_detail(
            ticket, terminal_ops,
            lineage=lineage,
            responsibility=responsibility,
            allowed_actions=allowed_actions,
            **article_actions,
            can_refine=refine["can_refine"],
            refine_options=refine["refine_options"],
            refine_denied_reason=refine["refine_denied_reason"],
            node_context=node_context,
            current_form=current_form,
        )
    )


@router.post("/tickets/{ticket_id}/refine", response_model=TicketCreateResponse)
async def refine_ticket_category(
    ticket_id: int,
    body: TicketRefine,
    db: AsyncSession = Depends(get_db),
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(get_current_user),
):
    """分诊：判断人把工单分类细化一级（权限/校验/链重算收口在 apply_refine）。"""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise NotFoundError("工单", ticket_id)

    context = await resolve_node_context(db, ticket, user)
    if await resolve_form(db, context):
        raise HTTPException(409, detail="当前分诊节点须连同分诊表单一起提交")

    await apply_refine(db, ticket, new_category_id=body.category_id, operator=user)
    await db.commit()
    return await _detail_after_mutation(db, ticket_id, user, cat_idx.lineage, cat_idx.responsibility)


class TriageSubmissionIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_category_id: int
    form_definition_id: int
    form_version: int
    values: dict[str, Any] = Field(default_factory=dict)


@router.get("/tickets/{ticket_id}/current-form")
async def get_current_form(
    ticket_id: int,
    target_category_id: int | None = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None:
        raise NotFoundError("工单", ticket_id)
    context = await resolve_node_context(db, ticket, user)
    can_read = (
        (context.node_type == "triage" and any(a["action"] == "refine" for a in context.allowed_actions))
        or (context.node_type in ("processing", "phone_feedback", "sales_opportunity") and compute_article_actions(ticket, user)["can_reply"])
    )
    if not can_read:
        raise HTTPException(403, detail="当前无节点表单权限")
    if context.node_type in ("processing", "phone_feedback", "sales_opportunity") and target_category_id is not None:
        raise HTTPException(400, detail="当前节点表单无需目标分类")
    if target_category_id is not None:
        options = (await refine_capability(db, ticket, user))["refine_options"]
        if target_category_id not in {option["id"] for option in options}:
            raise HTTPException(400, detail="只能选择当前分类的启用直下级")
    form = await resolve_form(db, context)
    if form is None:
        raise HTTPException(404, detail="当前节点未配置已发布表单")
    return await present_form(db, form, ticket, target_category_id)


@router.get("/tickets/{ticket_id}/node-submissions")
async def get_node_submissions(
    ticket_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Read submission history using the captured field definitions, not latest form config."""
    ticket = await db.get(Ticket, ticket_id)
    if ticket is None or (ticket.is_draft and ticket.creator_id != user.id):
        raise NotFoundError("工单", ticket_id)
    records = (await db.execute(select(TicketNodeSubmission).where(
        TicketNodeSubmission.ticket_id == ticket_id
    ).order_by(TicketNodeSubmission.id))).scalars().all()
    form_ids = {record.form_definition_id for record in records}
    operator_ids = {record.operator_id for record in records}
    form_rows = (await db.execute(
        select(FormDefinition.id, FormDefinition.code, FormDefinition.name).where(FormDefinition.id.in_(form_ids))
    )).all() if form_ids else []
    form_details = {form_id: (code, name) for form_id, code, name in form_rows}
    operator_names = dict((await db.execute(
        select(User.id, User.name).where(User.id.in_(operator_ids))
    )).all()) if operator_ids else {}
    article_ids = [record.article_id for record in records if record.article_id is not None]
    articles = {}
    if article_ids:
        for article in (await db.execute(select(Article).options(selectinload(Article.attachments)).where(
            Article.id.in_(article_ids)
        ))).scalars().all():
            articles[article.id] = article
    from app.api.v1.articles import _attachment_url
    return [{
        "id": record.id, "node_type": record.node_type,
        "form_code": form_details.get(record.form_definition_id, (None, None))[0],
        "form_name": form_details.get(record.form_definition_id, (None, None))[1],
        "operator_name": operator_names.get(record.operator_id),
        "form_definition_id": record.form_definition_id, "form_version": record.form_version,
        "department_id": record.department_id, "operator_id": record.operator_id,
        "submitted_at": record.submitted_at, "action_type": record.action_type,
        "state_log_id": record.state_log_id, "data": record.data,
        "article_id": record.article_id,
        "article_body": articles[record.article_id].body if record.article_id in articles else None,
        "attachments": [{"id": att.id, "filename": att.original_filename,
                         "url": _attachment_url(att.storage_path)}
                        for att in articles[record.article_id].attachments] if record.article_id in articles else [],
        "field_snapshot": record.field_snapshot,
    } for record in records]


@router.post("/tickets/{ticket_id}/node-submit", response_model=TicketCreateResponse)
async def submit_node_form(
    ticket_id: int,
    payload: str = Form(...),
    attachments: list[UploadFile] = File(default=[]),
    db: AsyncSession = Depends(get_db),
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(get_current_user),
):
    """Complete a processing, feedback, or sales node through domain transitions."""
    try:
        body = json.loads(payload)
        if not isinstance(body, dict) or not isinstance(body.get("values"), dict):
            raise ValueError
        form_id = int(body["form_definition_id"])
        form_version = int(body["form_version"])
    except (ValueError, TypeError, KeyError):
        raise HTTPException(422, detail="节点表单请求格式错误") from None
    ticket = (await db.execute(select(Ticket).where(Ticket.id == ticket_id).with_for_update())).scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("工单", ticket_id)
    if (body.get("expected_category_id") != ticket.category_id
            or body.get("expected_department_id") != ticket.skill_group_id
            or body.get("expected_dispatch_step_index") != ticket.dispatch_step_index
            or body.get("expected_state") != ticket.state):
        raise HTTPException(409, detail="工单上下文已变化，请刷新后重新提交")
    context = await resolve_node_context(db, ticket, user)
    if context.node_type not in ("processing", "phone_feedback", "sales_opportunity"):
        raise HTTPException(409, detail="当前节点已变化或不是可提交节点")
    form = await resolve_form(db, context)
    if form is None:
        raise HTTPException(409, detail="当前处理节点未配置表单")
    # Same ownership rule as the existing reply endpoint; no extra role grants.
    if ticket.owner_id != user.id or not compute_article_actions(ticket, user)["can_reply"]:
        raise HTTPException(403, detail="仅当前处理人可完成本节点处理")
    if (form_id, form_version) != (form.definition.id, form.definition.version):
        raise HTTPException(409, detail="表单版本已变化，请刷新后重新提交")
    if len(attachments) > 10:
        raise HTTPException(422, detail="最多上传 10 个相关材料附件")
    data, ticket_updates, article_values, snapshot = await validate_submission(
        db, form, ticket, None, body["values"],
    )
    finance_owner_id: int | None = None
    if ticket.category_id == 2204 and context.department_code == "销售":
        expected_person = {"时空道宇": "姜敏", "青岛上合": "朱景升"}.get(data.get("finance_company"))
        if expected_person is None or data.get("finance_person") != expected_person:
            raise HTTPException(422, detail="财务所属公司与财务人员不匹配")
        finance_group = (await db.execute(select(SkillGroup).where(SkillGroup.name == "财务"))).scalar_one_or_none()
        if finance_group is None:
            raise HTTPException(422, detail="财务部门尚未配置")
        now = datetime.now(timezone.utc)
        finance_person = (await db.execute(select(User).join(
            UserSkillGroup, UserSkillGroup.user_id == User.id,
        ).where(
            User.name == expected_person, User.is_active.is_(True),
            UserSkillGroup.skill_group_id == finance_group.id,
            or_(UserSkillGroup.effective_from.is_(None), UserSkillGroup.effective_from <= now),
            or_(UserSkillGroup.effective_to.is_(None), UserSkillGroup.effective_to >= now),
        ))).scalar_one_or_none()
        if finance_person is None:
            raise HTTPException(422, detail="所选财务人员不是当前有效的财务部门成员")
        finance_owner_id = finance_person.id
    if not article_values.get("body", "").strip():
        raise HTTPException(422, detail="节点反馈正文必填")
    # The reply endpoint uses this log as the completed node's timeline key.
    handling_log = (await db.execute(select(TicketStateLog).where(
        TicketStateLog.ticket_id == ticket_id,
        TicketStateLog.to_state.in_(("open", "on_hold")),
    ).order_by(TicketStateLog.id.desc()).limit(1))).scalar_one_or_none()
    saved_attachments: list[ArticleAttachment] = []
    try:
        article = Article(ticket_id=ticket_id, type="reply", sender_id=user.id,
                          body=article_values["body"],
                          state_key=str(handling_log.id) if handling_log else None)
        db.add(article)
        await db.flush()
        if attachments:
            from app.api.v1.articles import _save_attachments
            saved_attachments = await _save_attachments(article.id, ticket_id, attachments, allow_pdf=True)
            db.add_all(saved_attachments)
            await db.flush()
        for key, value in ticket_updates.items():
            setattr(ticket, key, value)
        log = await apply_transition(db, ticket, to_state="resolved", operator=user,
                                     allow_intermediate_transfer=True,
                                     allow_sales_completion=context.node_type == "sales_opportunity")
        if finance_owner_id is not None:
            await apply_transition(db, ticket, to_state="open", operator=user,
                                   owner_id=finance_owner_id, dispatcher_id=finance_owner_id,
                                   allow_reconciliation_handoff=True)
        if context.node_type == "sales_opportunity":
            log = await apply_transition(db, ticket, to_state="archived", operator=user,
                                         allow_sales_completion=True)
        submission = TicketNodeSubmission(
            ticket_id=ticket.id, node_type=context.node_type, form_definition_id=form.definition.id,
            form_version=form.definition.version, department_id=context.department_id,
            operator_id=user.id, action_type=log.action_type, data=data,
            field_snapshot=snapshot, state_log_id=log.id, article_id=article.id,
        )
        db.add(submission)
        await db.commit()
    except Exception:
        await db.rollback()
        # The DB rollback removes attachment rows. Remove newly written files too.
        for directory in {Path(att.storage_path).parent for att in saved_attachments}:
            from app.core.config import settings
            shutil.rmtree(Path(settings.UPLOAD_DIR) / directory, ignore_errors=True)
        raise
    return await _detail_after_mutation(db, ticket_id, user, cat_idx.lineage, cat_idx.responsibility)


@router.post("/tickets/{ticket_id}/triage-submit", response_model=TicketCreateResponse)
async def submit_triage(
    ticket_id: int,
    body: TriageSubmissionIn,
    db: AsyncSession = Depends(get_db),
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(get_current_user),
):
    """One locked transaction: validate form, save submission, refine and route."""
    ticket = (await db.execute(
        select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    )).scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("工单", ticket_id)
    context = await resolve_node_context(db, ticket, user)
    if context.node_type != "triage" or not any(a["action"] == "refine" for a in context.allowed_actions):
        raise HTTPException(403, detail="当前用户无权提交分诊")
    capability = await refine_capability(db, ticket, user)
    if body.target_category_id not in {option["id"] for option in capability["refine_options"]}:
        raise HTTPException(400, detail="只能细化到当前分类的启用直下级")
    form = await resolve_form(db, context)
    if form is None:
        raise HTTPException(409, detail="当前分诊节点未配置表单")
    if form.definition.code == "constellation_triage_v1":
        # The selected category is the only editable routing choice. Reject a
        # broken target chain before saving the form or changing the category.
        from app.services.dispatch_chain import get_dept, resolve_chain

        target_chain = await resolve_chain(db, body.target_category_id)
        target_steps = target_chain["steps"] if target_chain else []
        target_department = target_steps[0].get("department_code") if target_steps else None
        if not target_chain or target_chain["matched_category_id"] != body.target_category_id \
                or not target_department or target_department == context.department_code \
                or await get_dept(db, target_department) is None:
            raise HTTPException(422, detail="目标分类未配置有效的流转部门")
    if (body.form_definition_id, body.form_version) != (form.definition.id, form.definition.version):
        raise HTTPException(409, detail="表单版本已变化，请刷新后重新提交")
    data, ticket_updates, _article_values, snapshot = await validate_submission(
        db, form, ticket, body.target_category_id, body.values,
    )
    submission = TicketNodeSubmission(
        ticket_id=ticket.id, node_type="triage", form_definition_id=form.definition.id,
        form_version=form.definition.version, department_id=context.department_id,
        operator_id=user.id, action_type="refine", data=data, field_snapshot=snapshot,
    )
    db.add(submission)
    for key, value in ticket_updates.items():
        setattr(ticket, key, value)
    log = await apply_refine(db, ticket, new_category_id=body.target_category_id, operator=user)
    submission.state_log_id = log.id
    await db.commit()
    return await _detail_after_mutation(db, ticket_id, user, cat_idx.lineage, cat_idx.responsibility)


class ClosureSubmissionIn(BaseModel):
    form_definition_id: int
    form_version: int
    expected_category_id: int | None = None
    expected_department_id: int | None = None
    expected_dispatch_step_index: int | None = None
    expected_state: str
    values: dict[str, Any] = Field(default_factory=dict)


@router.post("/tickets/{ticket_id}/closure-submit", response_model=TicketCreateResponse)
async def submit_closure(
    ticket_id: int,
    body: ClosureSubmissionIn,
    db: AsyncSession = Depends(get_db),
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(get_current_user),
):
    """客服闭环回访：一把锁内校验表单、写 Ticket 真值、再走既有 archive 流转。

    锁 Ticket → 校验客户端期望上下文 → 重算 NodeContext → resolve_form →
    validate_submission → 写 Ticket 正式字段 → 写 Submission →
    apply_transition(archived) → TicketStateLog → commit。

    满意度不满的归档限制仍由 apply_transition 内的既有前置校验判定并整体回滚，
    表单本身不新增状态转换，也不直接写 status / closed_at。
    """
    ticket = (await db.execute(
        select(Ticket).where(Ticket.id == ticket_id).with_for_update()
    )).scalar_one_or_none()
    if ticket is None:
        raise NotFoundError("工单", ticket_id)
    if (
        body.expected_category_id != ticket.category_id
        or body.expected_department_id != ticket.skill_group_id
        or body.expected_dispatch_step_index != ticket.dispatch_step_index
        or body.expected_state != ticket.state
    ):
        raise HTTPException(409, detail="工单上下文已变化，请刷新后重新提交")
    context = await resolve_node_context(db, ticket, user)
    if context.node_type != "closure":
        raise HTTPException(409, detail="当前节点已变化或不是可闭环节点")
    form = await resolve_form(db, context)
    if form is None:
        raise HTTPException(409, detail="当前闭环节点未配置表单")
    # 归档权限仍由状态机唯一入口判定（含客服团队 / admin 口径）。
    await check_transition_permission(db, ticket, "archived", user)
    if (body.form_definition_id, body.form_version) != (form.definition.id, form.definition.version):
        raise HTTPException(409, detail="表单版本已变化，请刷新后重新提交")
    data, ticket_updates, _article_values, snapshot = await validate_submission(
        db, form, ticket, None, body.values,
        context=closure_condition_context(ticket),
    )
    previous_satisfaction = ticket.satisfaction
    for key, value in ticket_updates.items():
        setattr(ticket, key, value)
    # callback_required（是否要求回访）不在此改写：它在更早的流程已确定，
    # Closure 只记录回访事实（is_callbacked）。把它跟着 is_callbacked 同步会把
    # 「需要回访 = true / 已回访 = false」这个合法状态抹掉，并让 pending_callback
    # 统计失真。不满意事实同样由 apply_transition 的既有归档前置拦截。
    if ticket.satisfaction == "dissatisfied" and not (ticket.unsatisfied_reason or "").strip():
        raise HTTPException(422, detail="客户不满意：必须填写不满意原因")
    if ticket.customer_recognized is False and not (ticket.unsatisfied_reason or "").strip():
        raise HTTPException(422, detail="客户不认可处理结果：必须填写不满原因")
    # 与单条 PATCH 同源：不满意评价不可原地改写为非不满意，必须退回重开后重新回访。
    if previous_satisfaction == "dissatisfied" and ticket.satisfaction != "dissatisfied":
        raise HTTPException(
            422, detail="客户不满意：需退回重新处理并完成新一次回访后才能变更评价")
    submission = TicketNodeSubmission(
        ticket_id=ticket.id, node_type="closure", form_definition_id=form.definition.id,
        form_version=form.definition.version, department_id=context.department_id,
        operator_id=user.id, action_type="archive", data=data, field_snapshot=snapshot,
    )
    db.add(submission)
    # 归档前置用「应用本次表单后」的工单判定：已完成回访则一步闭环，
    # 未完成 / 客户不满意则只固化回访事实、不流转状态，等下一次提交再关单。
    if transition_precondition_error(ticket, "archived") is None:
        log = await apply_transition(db, ticket, to_state="archived", operator=user)
        submission.state_log_id = log.id if log else None
    else:
        submission.action_type = "callback_record"
    await db.commit()
    return await _detail_after_mutation(db, ticket_id, user, cat_idx.lineage, cat_idx.responsibility)


@router.post("/tickets", response_model=TicketCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(require_role("admin", "agent")),
):
    """Create a new ticket."""
    warnings = None
    if body.category_id is not None and not await is_valid_ticket_category(db, body.category_id):
        raise HTTPException(422, detail="当前问题分类还需继续细化，或不能由客服建单选择")
    is_instant_consult = body.category_id == INSTANT_CONSULT_CATEGORY_ID
    if body.is_instant_resolve and not is_instant_consult:
        raise HTTPException(422, detail="只有即时办结咨询分类可以创建时办结")
    if is_instant_consult and body.is_opportunity:
        raise HTTPException(422, detail="即时办结咨询不能作为线索工单")
    if is_instant_consult:
        body.is_opportunity = False
        body.priority = "p4_enterprise"
        body.skill_group_id = None
        body.handler_skill_group_id = None
        body.dispatcher_id = None
        if not body.is_draft and not body.description.strip():
            raise HTTPException(422, detail="请填写咨询内容")
        if not body.is_draft and not (body.instant_resolution or "").strip():
            raise HTTPException(422, detail="请填写即时答复内容")
        body.instant_resolution = (body.instant_resolution or "").strip() or None

    if not body.is_draft:
        if not body.customer_phone.strip():
            raise HTTPException(422, detail="来电号码不能为空")
        if body.intake_form:
            lineage = cat_idx.lineage.get(body.category_id) if body.category_id else None
            root_id = lineage.l1.id if lineage and lineage.l1 else None
            if not body.is_opportunity:
                active_categories = list((await db.execute(
                    select(TicketCategory).where(TicketCategory.is_active.is_(True))
                )).scalars().all())
                chain_ids = set((await db.execute(
                    select(DispatchChain.category_id).where(DispatchChain.enabled.is_(True))
                )).scalars().all())
                selectable = create_selectable_categories(active_categories, chain_ids)
                if not selectable.get(body.category_id, False):
                    raise HTTPException(422, detail="当前问题分类还需继续细化，或不能由客服建单选择")
            required = {"客户问题详情": body.description}
            if not is_instant_consult:
                required.update({"客户名称": body.customer_name, "单位全称": body.customer_company,
                                 "行业": body.industry})
            if body.is_opportunity and not body.contact_phone:
                required["联系号码"] = body.contact_phone
            missing = [label for label, value in required.items() if not value]
            if body.is_opportunity is None and not is_instant_consult:
                missing.append("是否为线索工单")
            if not body.is_opportunity and root_id in (2201, 2301) and not body.satellite_number:
                missing.append("卫星物联网码号")
            if not body.is_opportunity and root_id == 2301:
                for label, value in (
                    ("故障发生时间", body.fault_occurred_at),
                    ("故障复现规律", body.fault_recurrence),
                    ("故障发生地理位置", body.fault_location),
                    ("是否批量故障", body.is_batch_fault),
                ):
                    if value is None or value == "":
                        missing.append(label)
            if missing:
                raise HTTPException(422, detail=f"请填写：{'、'.join(missing)}")
            if not body.is_opportunity and root_id not in (1001, 2101, 2201, 2301):
                raise HTTPException(422, detail="请选择有效的一级分类")
            if body.priority not in ("p1_urgent", "p2_high", "p3_normal", "p4_enterprise"):
                raise HTTPException(422, detail="优先级无效")
            if len(body.description) > 1000:
                raise HTTPException(422, detail="客户问题详情不能超过1000字")
            if (body.industry or not is_instant_consult) and body.industry not in ("海洋渔业", "工程机械", "智能网联", "交通物流", "能源行业", "应急通信", "智慧林草", "低空出行", "智慧水利", "智慧农业", "Robotaxi", "未提供"):
                raise HTTPException(422, detail="行业无效")
            if not body.is_opportunity and root_id == 2301 and body.fault_recurrence not in ("必现", "偶发", "仅特定时段"):
                raise HTTPException(422, detail="故障复现规律无效")
            if not re.fullmatch(r"(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8})", body.customer_phone):
                raise HTTPException(422, detail="来电号码格式不正确")
            if body.contact_phone and not re.fullmatch(r"(?:1[3-9]\d{9}|0\d{2,3}-?\d{7,8})", body.contact_phone):
                raise HTTPException(422, detail="联系号码格式不正确")
            if body.customer_email and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", body.customer_email):
                raise HTTPException(422, detail="邮箱格式不正确")
            body.complaint_level = (
                {"一般投诉": "一般", "重要投诉": "重要", "重大投诉": "重大"}.get(lineage.l2.name)
                if not body.is_opportunity and root_id == 2101 and lineage and lineage.l2 else None
            )
            if root_id != 2301:
                body.priority = "p4_enterprise"
            if body.is_opportunity or root_id != 2301:
                body.fault_occurred_at = None
                body.fault_recurrence = None
                body.fault_location = None
                body.is_batch_fault = None
            if body.is_opportunity:
                body.category_id = None
                body.satellite_number = None
                body.expected_result = None

    is_reconciliation = body.category_id == 2204 and not body.is_opportunity
    if (body.is_opportunity or is_reconciliation) and not body.is_draft:
        sales_group = await _sales_group_for_owner(db, body.sales_owner_id)
        body.skill_group_id = sales_group.id
        body.handler_skill_group_id = sales_group.id
        body.dispatcher_id = None


    # Auto-match responsibility：分派链（表A dispatch_chains）优先，
    # 无链回退旧 category_routing_rules（双轨过渡，设计 §8.3）。
    # body.* wins; 规则/链只填调用方留空的字段。
    auto_match_warning: str | None = None
    chain_steps: list[dict] | None = None
    # 是否需要回访由分类规则决定，与「是否已完成回访」无关（callback_policy）。
    callback_required = await resolve_callback_required(db, body.category_id)
    if is_reconciliation:
        chain_steps = [
            {"order": 1, "department_code": "销售"},
            {"order": 2, "department_code": "财务"},
        ]

    if body.category_id is not None and not is_reconciliation and not is_instant_consult:
        from app.services.dispatch_chain import resolve_responsibility
        resp = await resolve_responsibility(db, body.category_id)
        chain_steps = resp.get("chain_steps")
        if resp.get("matched"):
            if body.skill_group_id is None and resp.get("dispatcher_skill_group_id"):
                body.skill_group_id = resp["dispatcher_skill_group_id"]
            if body.handler_skill_group_id is None:
                # Even when the rule has no professional department we still
                # leave handler_skill_group_id as the caller set it.
                body.handler_skill_group_id = resp.get("handler_skill_group_id")
            if body.dispatcher_id is None and resp.get("dispatcher_id"):
                body.dispatcher_id = resp["dispatcher_id"]
            # Note: owner_id is NOT auto-assigned here; the chain's default
            # owner is used by the dispatcher's "分派" step, not at creation.
            if resp.get("reason"):
                auto_match_warning = resp["reason"]
        else:
            auto_match_warning = resp.get("reason")

        # 业务保障是售后的下一级问题判断入口。直接落给链首对接人，
        # 不允许建单时手动选出的其他部门/人员覆盖判断责任。
        if body.category_id == 2301 and resp.get("via") == "chain" and resp.get("dispatcher_id"):
            body.skill_group_id = resp.get("dispatcher_skill_group_id")
            body.handler_skill_group_id = resp.get("handler_skill_group_id")
            body.dispatcher_id = resp.get("dispatcher_id")

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
            industry=body.industry, customer_email=body.customer_email,
            satellite_number=body.satellite_number, is_opportunity=body.is_opportunity,
            expected_result=body.expected_result, fault_occurred_at=body.fault_occurred_at,
            fault_recurrence=body.fault_recurrence, fault_location=body.fault_location,
            is_batch_fault=body.is_batch_fault,
            region_id=body.region_id, region_name=body.region_name, category_id=body.category_id,
            group_id=body.group_id or user.group_id,
            skill_group_id=body.skill_group_id,
            handler_skill_group_id=body.handler_skill_group_id,
            owner_id=body.sales_owner_id if (body.is_opportunity or is_reconciliation) else None,
            creator_id=user.id, first_owner_id=None,
            dispatcher_id=None if (body.is_opportunity or is_reconciliation) else body.dispatcher_id,
            is_duplicate=body.is_duplicate,
            duplicate_reason=body.duplicate_reason,
            root_cause=body.root_cause,
            solution=body.solution,
            resolution=body.instant_resolution if is_instant_consult else None,
            complaint_level=body.complaint_level,
            dispatch_chain_steps=chain_steps,
            dispatch_step_index=0 if chain_steps else None,
            callback_required=callback_required,
            is_draft=True,
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
        solution_deadline = None

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
        if not body.dispatcher_id and not (body.is_opportunity or is_reconciliation or is_instant_consult):
            detail = "所选分类尚未配置对接人，请联系管理员" if body.intake_form else "建单时必须指定部门对接人"
            raise HTTPException(422, detail=detail)

        ticket = Ticket(
            number=number, description=body.description,
            priority=body.priority, channel=body.channel,
            state="pending",
            customer_type=body.customer_type, customer_name=body.customer_name,
            customer_phone=body.customer_phone, customer_phone_type=body.customer_phone_type, contact_phone=body.contact_phone,
            customer_company=body.customer_company,
            customer_level=body.customer_level, device_sn=body.device_sn,
            industry=body.industry, customer_email=body.customer_email,
            satellite_number=body.satellite_number, is_opportunity=body.is_opportunity,
            expected_result=body.expected_result, fault_occurred_at=body.fault_occurred_at,
            fault_recurrence=body.fault_recurrence, fault_location=body.fault_location,
            is_batch_fault=body.is_batch_fault,
            region_id=body.region_id, region_name=body.region_name, category_id=body.category_id,
            group_id=body.group_id or user.group_id,
            skill_group_id=body.skill_group_id,
            handler_skill_group_id=body.handler_skill_group_id,
            owner_id=None,
            creator_id=user.id, first_owner_id=None,
            dispatcher_id=None if is_reconciliation else body.dispatcher_id,
            is_duplicate=body.is_duplicate,
            duplicate_reason=body.duplicate_reason,
            root_cause=body.root_cause,
            solution=body.solution,
            resolution=body.instant_resolution if is_instant_consult else None,
            complaint_level=body.complaint_level,
            solution_deadline=solution_deadline,
            dispatch_chain_steps=chain_steps,
            dispatch_step_index=0 if chain_steps else None,
            callback_required=callback_required,
            is_draft=False,
        )

    db.add(ticket)
    await db.flush()  # to get ticket.id

    # 初始状态日志：仅正式工单记录（None → pending），草稿不写日志
    if not body.is_draft:
        await start_round(db, ticket, is_instant=is_instant_consult)
        await apply_initial_state(db, ticket, to_state="archived" if is_instant_consult else "pending",
                                  operator=user, body=body)
        if is_instant_consult:
            ticket.resolved = True
            ticket.solved_at = ticket.closed_at
            ticket.first_response_at = ticket.closed_at
        elif body.is_opportunity or is_reconciliation:
            await apply_transition(db, ticket, to_state="open", operator=user,
                                   owner_id=body.sales_owner_id, allow_sales_intake=True)

    await db.flush()
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
        data=_ticket_to_detail(ticket, lineage=cat_idx.lineage, responsibility=cat_idx.responsibility),
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
    cat_idx: CategoryIndexes = Depends(get_category_indexes),
    user: User = Depends(get_current_user),
):
    """Update ticket fields (state, priority, owner, etc.)."""
    result = await db.execute(select(Ticket).where(Ticket.id == ticket_id))
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise NotFoundError("工单", ticket_id)
    # callback_required 是系统维护字段：由分类规则在建单/分诊时确定（callback_policy），
    # 客户端不能人工修改——否则「是否要求回访」会和「是否已完成回访」重新混淆。
    if body.callback_required is not None:
        raise HTTPException(422, detail="是否需要回访由系统按问题分类确定，不能人工修改")

    if body.state == "resolved" or body.root_cause is not None:
        context = await resolve_node_context(db, ticket, user)
        if context.node_type == "processing" and await resolve_form(db, context):
            raise HTTPException(409, detail="当前处理节点须通过结构化处理表单提交")
    # 闭环节点已绑定表单后，archive 只能经 closure-submit：旧 PATCH 不能绕过必填项。
    if body.state == "archived":
        context = await resolve_node_context(db, ticket, user)
        if context.node_type == "closure" and await resolve_form(db, context):
            raise HTTPException(409, detail="当前闭环节点须通过结构化回访归档表单提交")

    # 回访/归档闭环字段先于状态流转应用：apply_transition 的归档前置校验
    # （satisfaction=dissatisfied 不得归档）必须基于同一请求中"应用后"的
    # 最终值判定，否则 state+满意度同发会绕过规则。
    if body.archive_notes is not None:
        ticket.archive_notes = body.archive_notes
    if body.callback_details is not None:
        # 回访详情：不满意原因 / 回访记录（V0.86 贯通前后端）
        ticket.callback_details = body.callback_details
    if body.is_callbacked is not None:
        ticket.is_callbacked = body.is_callbacked
        # 未回访时清空满意度；避免历史脏数据。
        # 例外：已产生的"不满意"回访事实不可被抹掉 —— 只能经"退回重开处理"
        # 这一合法流程（reopen 副作用清空满意度）重置
        if body.is_callbacked is False and ticket.satisfaction != "dissatisfied":
            ticket.satisfaction = None
            ticket.unsatisfied_reason = None  # 随满意度一起清（未回访/未产生不满意事实）
    if body.callback_required is not None:
        ticket.callback_required = body.callback_required
        # callback_required 是"是否要求回访"的流程配置，不是删除既有回访结果的
        # 开关：仅当尚未产生回访事实（is_callbacked=true）时才同步标记并清空；
        # 已回访（含 dissatisfied）的 is_callbacked/satisfaction/callback_details
        # 全部保留，dissatisfied 仍被归档前置拦截
        if (
            body.callback_required is False
            and ticket.is_callbacked is not True
            and ticket.satisfaction != "dissatisfied"
        ):
            ticket.is_callbacked = False
            ticket.satisfaction = None
            ticket.unsatisfied_reason = None
    if body.unsatisfied_reason is not None:
        # 不满意原因（设计 §8.2 #9）：dissatisfied 时必填；允许对已有不满意
        # 回访补录/修正原因（与满意度不同，原因不走"不可原地改写"限制）
        ticket.unsatisfied_reason = body.unsatisfied_reason.strip() or None
    if body.satisfaction is not None:
        # 校验：satisfaction 仅在 is_callbacked=true 时有意义
        allowed = {"satisfied", "average", "dissatisfied", "unrated"}
        if body.satisfaction not in allowed:
            raise HTTPException(422, detail=f"satisfaction 取值必须是 {sorted(allowed)} 之一")
        if ticket.is_callbacked is False:
            raise HTTPException(422, detail="未回访工单不能设置满意度")
        # 不满意评价不可原地改写：必须退回重开 → 重新处理 → 新一次回访
        # （重开副作用已清空 satisfaction），否则改个评分即可绕过归档限制
        if ticket.satisfaction == "dissatisfied" and body.satisfaction != "dissatisfied":
            raise HTTPException(422, detail="客户不满意：需退回重新处理并完成新一次回访后才能变更评价")
        ticket.satisfaction = body.satisfaction
        if body.satisfaction != "dissatisfied":
            # 新一轮回访为非不满意：不满意原因随之清空（模型注释的生命周期约定）
            ticket.unsatisfied_reason = None

    # 不满意原因一致性校验：最终满意度为 dissatisfied 时必须有原因。
    # 置于状态流转之前，保证 state+满意度+原因同发时先拦截（422）。
    if ticket.satisfaction == "dissatisfied" and not (ticket.unsatisfied_reason or "").strip():
        raise HTTPException(422, detail="客户不满意：必须填写不满意原因")

    is_resubmit = ticket.state == "returned" and body.state == "pending"
    if body.category_id is not None and not is_resubmit:
        raise HTTPException(422, detail="仅退回后重新提交时可修改问题分类")
    if is_resubmit:
        from app.services.dispatch_chain import resolve_responsibility

        if body.owner_id is not None:
            raise HTTPException(422, detail="重新提交后须由对接人重新分派处理人")

        category_id = body.category_id or ticket.category_id
        if category_id is not None and not await is_valid_ticket_category(db, category_id):
            raise HTTPException(422, detail="当前问题分类还需继续细化，或不能由客服建单选择")
        routing = await resolve_responsibility(db, category_id) if category_id is not None else {}
        steps = routing.get("chain_steps") or None
        # 有链时责任部门必须与链首一致；无链时才允许人工指定。
        if steps:
            skill_group_id = routing.get("dispatcher_skill_group_id")
            dispatcher_id = routing.get("dispatcher_id")
        else:
            skill_group_id = body.skill_group_id or routing.get("dispatcher_skill_group_id") or ticket.skill_group_id
            dispatcher_id = body.dispatcher_id or routing.get("dispatcher_id") or ticket.dispatcher_id
        if not skill_group_id or not dispatcher_id:
            raise HTTPException(422, detail="所选分类缺少对接部门或部门对接人")
        if not await is_dispatcher(db, dispatcher_id, skill_group_id):
            raise HTTPException(422, detail="所选人员不是该部门的对接人")
        ticket.category_id = category_id
        ticket.callback_required = await resolve_callback_required(db, category_id)
        ticket.dispatch_chain_steps = steps
        ticket.dispatch_step_index = 0 if steps else None
        ticket.return_checkpoints = []
        ticket.legacy_return_cursor_log_id = None
        ticket.first_owner_id = None
        ticket.skill_group_id = skill_group_id
        ticket.handler_skill_group_id = routing.get("handler_skill_group_id") or skill_group_id
        ticket.dispatcher_id = dispatcher_id
        body.skill_group_id = skill_group_id
        body.handler_skill_group_id = ticket.handler_skill_group_id
        body.dispatcher_id = dispatcher_id
        # 分类变化沿用当前计时轮次的起点，稍后统一按新规则更新截止时间。
        db.expire(ticket, ["category", "skill_group", "handler_skill_group", "dispatcher", "first_owner"])

    # State transition — 唯一执行入口：校验/权限/reason/前置校验/副作用/Flow Log 收口
    # （业务约束改写、resolved→on_hold 兜底、归档闭环校验见 state_machine.apply_transition）
    if body.state is not None and body.state == ticket.state \
            and ticket.state == "on_hold":
        # 同状态 PATCH 通常是 no-op，但 on_hold→on_hold 会被误读为
        # 「已修改预计恢复时间」。调整时间必须先恢复处理再重新暂缓。
        raise HTTPException(
            422, detail="已在暂缓中；如需调整预计恢复时间，请先恢复处理再重新暂缓")

    if body.priority is not None:
        sla_root = await root_category(db, ticket.category_id)
        ticket.priority = body.priority if sla_root and sla_root.name == "业务保障" else "p4_enterprise"
    if body.complaint_level is not None:
        ticket.complaint_level = body.complaint_level
    if ticket.solved_at is None and (is_resubmit or body.priority is not None or body.complaint_level is not None):
        await replace_running_deadline(db, ticket)

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
    return _ticket_to_detail(ticket, lineage=cat_idx.lineage, responsibility=cat_idx.responsibility)


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
    if body.updates.category_id is not None:
        raise HTTPException(422, detail="问题分类只能在单张工单重新提交时修改")
    result = await db.execute(
        select(Ticket).where(Ticket.id.in_(body.ticket_ids))
    )
    tickets = result.scalars().all()
    if body.updates.state == "resolved":
        for ticket in tickets:
            context = await resolve_node_context(db, ticket, user)
            if context.node_type == "processing" and await resolve_form(db, context):
                raise HTTPException(409, detail="批量操作不能绕过当前处理节点表单")
    if body.updates.state == "archived":
        for ticket in tickets:
            context = await resolve_node_context(db, ticket, user)
            if context.node_type == "closure" and await resolve_form(db, context):
                raise HTTPException(409, detail="批量操作不能绕过当前闭环归档表单")
    updated = 0
    for ticket in tickets:
        # 先应用非 state 字段（owner/dsp/group/skill_group/priority），这样流转快照
        # 写入时 ticket 已携带新值
        if body.updates.priority is not None:
            sla_root = await root_category(db, ticket.category_id)
            ticket.priority = body.updates.priority if sla_root and sla_root.name == "业务保障" else "p4_enterprise"
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
        if body.updates.priority is not None and ticket.solved_at is None:
            await replace_running_deadline(db, ticket)
        if (body.updates.state is not None
                and body.updates.state == ticket.state
                and ticket.state == "on_hold"):
            raise HTTPException(
                422, detail="已在暂缓中；如需调整预计恢复时间，请先恢复处理再重新暂缓")
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
            # resubmit/archive/cancel/instant_resolve。
            # 历史日志列值为 null 时按真实流转表推导（前端不再自算流转规则）
            "action_type": log.action_type or action_for(log.from_state, log.to_state),
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return {"data": data}
