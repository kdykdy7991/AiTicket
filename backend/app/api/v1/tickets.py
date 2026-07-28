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
)
from app.services.state_machine import validate_transition

router = APIRouter(tags=["tickets"])

# Chinese labels for states
STATE_LABELS = {
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


def _snapshot_people(ticket: Ticket, body=None) -> dict:
    """写入 state_log 时的人员快照：进入新状态那一刻工单上的创建者/对接人/处理人。

    body 字段优先（代表正在应用的新值），未提供则回退到 ticket 当前值。
    - creator_id 永不变，直接取 ticket
    - dispatcher / owner：resubmit / 重新指派等场景下 body 会带新值
    """
    return {
        "creator_id_snapshot": ticket.creator_id,
        "dispatcher_id_snapshot": (
            body.dispatcher_id if body is not None and body.dispatcher_id is not None
            else ticket.dispatcher_id
        ),
        "owner_id_snapshot": (
            body.owner_id if body is not None and body.owner_id is not None
            else ticket.owner_id
        ),
    }


def _enforce_business_constraints(ticket: Ticket, target_state: str) -> str:
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


def _ticket_to_brief(t: Ticket) -> TicketBrief:
    return TicketBrief(
        id=t.id, number=t.number, state=t.state,
        priority=t.priority, channel=t.channel, customer_type=t.customer_type,
        customer_name=t.customer_name, customer_phone=t.customer_phone, customer_phone_type=t.customer_phone_type, contact_phone=t.contact_phone,
        skill_group_id=t.skill_group_id,
        skill_group_name=t.skill_group.name if t.skill_group else None,
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
        sla_solution_breached=t.sla_solution_breached,
        solution_deadline=t.solution_deadline,
        urged_at=t.urged_at,
        urged_by_id=t.urged_by_id,
        urged_by_name=t.urged_by.name if t.urged_by else None,
        has_addition=t.has_addition,
        has_returned=t.has_returned,
        created_at=t.created_at, updated_at=t.updated_at,
    )


def _ticket_to_detail(t: Ticket) -> TicketDetail:
    brief = _ticket_to_brief(t)
    return TicketDetail(
        **brief.model_dump(),
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
        group_id=t.group_id,
        group_name=t.group.name if t.group else None,
        returned_to_user_id=t.returned_to_user_id,
        returned_to_user_name=t.returned_to_user.name if t.returned_to_user else None,
        callback_required=t.callback_required,
        callback_details=t.callback_details,
        archive_notes=t.archive_notes,
    )


async def _calculate_sla_deadline(db: AsyncSession, priority: str, skill_group_id: int | None) -> datetime | None:
    """Look up SLA policy and compute solution deadline."""
    # Try group+priority first, then global
    for sg_id in [skill_group_id, None]:
        result = await db.execute(
            select(SLAPolicy).where(
                SLAPolicy.skill_group_id == sg_id,
                SLAPolicy.priority == priority,
            )
        )
        policy = result.scalar_one_or_none()
        if policy:
            return datetime.now(timezone.utc) + timedelta(minutes=policy.solution_minutes)
    return None


async def _is_dispatcher(db: AsyncSession, user_id: int, skill_group_id: int | None) -> bool:
    """检查用户是否为某对接部门的部门对接人。"""
    if not skill_group_id:
        return False
    from app.models.group import UserSkillGroup
    result = await db.execute(
        select(UserSkillGroup).where(
            UserSkillGroup.user_id == user_id,
            UserSkillGroup.skill_group_id == skill_group_id,
            UserSkillGroup.is_dispatcher == True,
        )
    )
    return result.scalar_one_or_none() is not None


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


async def check_transition_permission(db: AsyncSession, ticket: Ticket, to_state: str, user: User, owner_id: int | None = None):
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
    from app.core.exceptions import ForbiddenError
    if user.role == "admin":
        return  # admin 全权限

    from_state = ticket.state

    # 分派：部门对接人
    if from_state == "pending" and to_state == "open":
        if not await _is_dispatcher(db, user.id, ticket.skill_group_id):
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
        if await _is_dispatcher(db, user.id, ticket.skill_group_id):
            return
        raise ForbiddenError("只有部门对接人可退回待受理工单")

    # 已退回工单：创建者可重新提交或撤销
    if from_state == "returned" and to_state in ("pending", "cancelled"):
        if ticket.creator_id == user.id:
            return
        raise ForbiddenError("只有创建者可处理已退回工单")

    raise ForbiddenError("无权执行此状态变更")


@router.get("/tickets")
async def list_tickets(
    state: str | None = None,
    priority: str | None = None,
    skill_group_id: int | None = None,
    owner_id: int | None = None,
    group_id: int | None = None,
    category_id: int | None = None,
    customer_type: str | None = None,
    is_duplicate: bool | None = None,
    is_callbacked: bool | None = None,
    is_overdue: bool | None = None,
    keyword: str | None = None,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List tickets with filters and pagination."""
    # 默认不过滤草稿
    query = select(Ticket).options(
        selectinload(Ticket.owner), selectinload(Ticket.skill_group),
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

    return {
        "data": [_ticket_to_brief(t).model_dump() for t in tickets],
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
    group_id: int | None = None,
    category_id: int | None = None,
    customer_type: str | None = None,
    is_duplicate: bool | None = None,
    is_callbacked: bool | None = None,
    is_overdue: bool | None = None,
    keyword: str | None = None,
    columns: str | None = Query(None, description="逗号分隔的列组：base,customer,category,workflow"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """导出工单为 CSV（真实数据，按当前筛选条件）。"""
    from app.models.group import Group, SkillGroup
    from app.models.category import TicketCategory
    from app.models.user import User as UserModel

    query = (
        select(Ticket)
        .options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
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

    # 列定义：(表头, 取值函数)
    col_defs: list[tuple[str, any]] = []
    if "base" in col_groups:
        col_defs += [
            ("工单编号", lambda t: t.number),
            ("创建时间", lambda t: t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else ""),
            ("结案时间", lambda t: t.closed_at.strftime("%Y-%m-%d %H:%M") if t.closed_at else ""),
            ("关闭时长(分)", lambda t: t.closed_duration_minutes or ""),
            ("当前状态", lambda t: state_labels.get(t.state, t.state)),
            ("工单来源", lambda t: channel_labels.get(t.channel, t.channel)),
        ]
    if "customer" in col_groups:
        col_defs += [
            ("用户姓名", lambda t: t.customer_name),
            ("联系手机号", lambda t: t.customer_phone),
            ("设备编号/SN", lambda t: t.device_sn or ""),
            ("用户类型", lambda t: customer_type_labels.get(t.customer_type, t.customer_type)),
        ]
    if "category" in col_groups:
        col_defs += [
            ("一级分类", lambda t: t.category.name if t.category else ""),
            ("故障现象描述", lambda t: t.symptom or ""),
            ("是否重复工单", lambda t: "是" if t.is_duplicate else "否"),
            ("优先级", lambda t: priority_labels.get(t.priority, t.priority)),
        ]
    if "workflow" in col_groups:
        col_defs += [
            ("首次受理坐席", lambda t: t.first_owner_id or ""),
            ("对接部门", lambda t: t.skill_group.name if t.skill_group else ""),
            ("SLA是否达标", lambda t: "超时" if t.sla_solution_breached else "达标"),
            ("处理备注", lambda t: t.resolution or ""),
            ("是否解决", lambda t: "是" if t.resolved else "否"),
            ("归档备注", lambda t: t.archive_notes or ""),
            ("是否回访", lambda t: "是" if t.is_callbacked else "否"),
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
            selectinload(Ticket.owner), selectinload(Ticket.skill_group),
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

    db.add(TicketStateLog(
        ticket_id=ticket.id, from_state=None, to_state="pending",
        operator_id=user.id,
        **_snapshot_people(ticket, body),
    ))
    await db.commit()

    result = await db.execute(
        select(Ticket).options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
            selectinload(Ticket.skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
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
            selectinload(Ticket.skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
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
            selectinload(Ticket.skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
            selectinload(Ticket.group), selectinload(Ticket.urged_by),
        )
        .where(Ticket.id == ticket_id)
    )
    ticket = result.scalar_one_or_none()
    if not ticket:
        raise NotFoundError("工单", ticket_id)
    return _ticket_to_detail(ticket)


@router.post("/tickets", response_model=TicketCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    body: TicketCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    """Create a new ticket."""
    warnings = None

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
            skill_group_id=body.skill_group_id, owner_id=None,
            creator_id=user.id, first_owner_id=None,
            dispatcher_id=body.dispatcher_id,
            is_duplicate=body.is_duplicate,
            duplicate_reason=body.duplicate_reason,
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
        solution_deadline = await _calculate_sla_deadline(db, body.priority, body.skill_group_id)

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
            skill_group_id=body.skill_group_id, owner_id=None,
            creator_id=user.id, first_owner_id=None,
            dispatcher_id=body.dispatcher_id,
            is_duplicate=body.is_duplicate,
            duplicate_reason=body.duplicate_reason,
            solution_deadline=solution_deadline,
            is_draft=False,
        )

    db.add(ticket)
    await db.flush()  # to get ticket.id

    # 初始状态日志：仅正式工单记录（→ pending）
    if not body.is_draft:
        db.add(TicketStateLog(
            ticket_id=ticket.id, from_state=None, to_state="pending",
            operator_id=user.id,
            **_snapshot_people(ticket, body),
        ))

    await db.refresh(ticket)

    # 显式提交，确保工单在返回前已持久化，避免前端立即跳转详情时 404
    await db.commit()

    # Reload with relationships
    result = await db.execute(
        select(Ticket).options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
            selectinload(Ticket.skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
            selectinload(Ticket.group),
        ).where(Ticket.id == ticket.id)
    )
    ticket = result.scalar_one()

    return TicketCreateResponse(data=_ticket_to_detail(ticket), warnings=warnings)


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

    now = datetime.now(timezone.utc)

    # State transition
    if body.state is not None and body.state != ticket.state:
        # 业务约束：resolved → on_hold 自动改写为 resolved → open
        # （前端按钮走的是 resolveReturnTarget 算出的目标，此处是兜底，
        #  防非前端路径误发"把已处理工单退回暂缓"）
        body = body.model_copy(update={"state": _enforce_business_constraints(ticket, body.state)})

        validate_transition(ticket.state, body.state)

        # 权限校验：不同操作限定不同角色
        await check_transition_permission(db, ticket, body.state, user, body.owner_id)

        from app.services.state_machine import requires_reason
        if requires_reason(ticket.state, body.state) and not body.reason:
            raise HTTPException(400, detail=f"从「{STATE_LABELS.get(ticket.state, ticket.state)}」变更为「{STATE_LABELS.get(body.state, body.state)}」需要填写原因")

        old_state = ticket.state

        # 先把"新状态"的人员字段调整到 ticket 上（owner/dsp 等），再写 state_log 取快照
        # 注意：state-based 副作用和 body 字段都在这里应用，body 中显式提供的字段优先
        if body.state == "open":
            if old_state == "pending":
                # 分派处理人：pending→open 时由对接人指定 owner_id
                ticket.first_owner_id = ticket.owner_id or user.id
            elif old_state == "returned":
                # 已退回工单重新提交：保持无处理人，等待再次分派
                ticket.returned_to_user_id = None
        elif body.state == "pending":
            # open→pending 退回 或 returned→pending 重新提交：待受理无处理人
            if old_state in ("open", "returned"):
                ticket.owner_id = None
                ticket.returned_to_user_id = None
        elif body.state == "on_hold":
            # on_hold←open（暂缓）/ on_hold←resolved（退回）：处理人保持不变
            # TODO(sla-policy): SLA 策略未定，暂不在进/出 on_hold 时调整 solution_deadline
            pass
        elif body.state == "resolved":
            ticket.solved_at = now
            ticket.resolved = True
            if ticket.solution_deadline and now > ticket.solution_deadline:
                ticket.sla_solution_breached = True
        elif body.state == "returned":
            # 仅 pending→returned：分配给创建工单的客服人员
            if old_state == "pending":
                ticket.returned_to_user_id = ticket.creator_id
                ticket.owner_id = ticket.creator_id
        elif body.state in ("archived", "cancelled"):
            # 终态：记录结案时间
            ticket.closed_at = now
            if ticket.created_at:
                ticket.closed_duration_minutes = int((now - ticket.created_at).total_seconds() / 60)

        # 应用 body 中显式提供的人员/部门字段（覆盖上面的副作用）
        if body.owner_id is not None:
            ticket.owner_id = body.owner_id
        if body.dispatcher_id is not None:
            ticket.dispatcher_id = body.dispatcher_id

        # 暂缓：存 hold_until
        if body.state == "on_hold" and body.hold_until:
            from datetime import datetime as dt
            ticket.hold_until = dt.fromisoformat(body.hold_until).replace(tzinfo=timezone.utc)

        # has_returned 跟随"最新一次动作"：本次转换属于 RETURN_TRANSITIONS 才置 true
        ticket.has_returned = (old_state, body.state) in RETURN_TRANSITIONS
        ticket.state = body.state

        # Calculate duration in old state
        last_log = await db.execute(
            select(TicketStateLog)
            .where(TicketStateLog.ticket_id == ticket_id)
            .order_by(TicketStateLog.created_at.desc()).limit(1)
        )
        last = last_log.scalar_one_or_none()
        duration = None
        if last:
            duration = int((now - last.created_at).total_seconds() / 60)

        # Record state log（快照此时 ticket 已是"新状态"下的人员值）
        log = TicketStateLog(
            ticket_id=ticket.id, from_state=old_state, to_state=body.state,
            operator_id=user.id, reason=body.reason, duration_minutes=duration,
            **_snapshot_people(ticket, body),
        )
        db.add(log)
        # 注：has_returned 已在写 state_log 处按 RETURN_TRANSITIONS 同步，此处不再覆盖
    if body.archive_notes is not None:
        ticket.archive_notes = body.archive_notes
    if body.is_callbacked is not None:
        ticket.is_callbacked = body.is_callbacked
    if body.priority is not None:
        ticket.priority = body.priority
        # Recalculate SLA deadline (creation → resolved)
        if ticket.solved_at is None:
            ticket.solution_deadline = await _calculate_sla_deadline(db, body.priority, ticket.skill_group_id)

    if body.owner_id is not None:
        ticket.owner_id = body.owner_id
    if body.group_id is not None:
        ticket.group_id = body.group_id
    if body.skill_group_id is not None:
        ticket.skill_group_id = body.skill_group_id
    if body.dispatcher_id is not None:
        ticket.dispatcher_id = body.dispatcher_id

    await db.flush()

    # Reload with relationships
    result = await db.execute(
        select(Ticket).options(
            selectinload(Ticket.owner), selectinload(Ticket.creator), selectinload(Ticket.dispatcher),
            selectinload(Ticket.returned_to_user), selectinload(Ticket.first_owner),
            selectinload(Ticket.skill_group), selectinload(Ticket.category).selectinload(TicketCategory.parent),
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
    """Batch update tickets."""
    result = await db.execute(
        select(Ticket).where(Ticket.id.in_(body.ticket_ids))
    )
    tickets = result.scalars().all()
    updated = 0
    for ticket in tickets:
        # 先应用非 state 字段（owner/dsp/group/skill_group/priority），这样 state_log
        # 写快照时 ticket 已携带新值
        if body.updates.priority is not None:
            ticket.priority = body.updates.priority
        if body.updates.group_id is not None:
            ticket.group_id = body.updates.group_id
        if body.updates.skill_group_id is not None:
            ticket.skill_group_id = body.updates.skill_group_id
        if body.updates.owner_id is not None:
            ticket.owner_id = body.updates.owner_id
        if body.updates.dispatcher_id is not None:
            ticket.dispatcher_id = body.updates.dispatcher_id
        if body.updates.state is not None and body.updates.state != ticket.state:
            # 业务约束：resolved → on_hold 改写为 resolved → open（与 update_ticket 一致）
            to_state = _enforce_business_constraints(ticket, body.updates.state)
            try:
                validate_transition(ticket.state, to_state)
                from_state = ticket.state
                log = TicketStateLog(
                    ticket_id=ticket.id, from_state=from_state, to_state=to_state,
                    operator_id=user.id, reason=body.updates.reason,
                    **_snapshot_people(ticket, body.updates),
                )
                db.add(log)
                ticket.state = to_state
                # has_returned 跟随"最新一次动作"同步
                ticket.has_returned = (from_state, to_state) in RETURN_TRANSITIONS
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
            "created_at": log.created_at.isoformat() if log.created_at else None,
        })
    return {"data": data}
