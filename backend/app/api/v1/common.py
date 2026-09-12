"""人员、分系统（skill_groups）、枚举元数据与 POC 统计接口。

旧客服语义接口（dispatchers/handlers、客服组、工单分类、区域、SLA 策略）已下线。
"""

from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_any_role
from app.core.exceptions import NotFoundError
from app.core.security import hash_password
from app.domain.poc_workflow import (
    ALL_ROLES,
    BusinessRole,
    Priority,
    STATE_ORDER,
    TicketAction,
    TicketState,
    VerificationStatus,
)
from app.models.group import SkillGroup, UserSkillGroup
from app.models.ticket import Ticket
from app.models.user import User, UserRole
from app.schemas.common import (
    SkillGroupCreate,
    UserCreate,
    UserUpdate,
)
from app.services.notification import send_dingtalk_text
from app.services.poc_workflow import TERMINAL_VALUES, ticket_scope

# ── Users ─────────────────────────────────────────────────

users_router = APIRouter(tags=["users"])

ADMIN_ONLY = require_any_role(BusinessRole.ADMIN.value)


def _user_skill_groups(user: User) -> list[dict]:
    return [{"id": sg.id, "name": sg.name} for sg in (user.skill_groups or [])]


def _user_payload(user: User, *, full: bool) -> dict:
    data = {
        "id": user.id,
        "username": user.username,
        "name": user.name,
        "roles": user.roles,
        "skill_groups": _user_skill_groups(user),
        "is_active": user.is_active,
    }
    if full:
        data.update(
            {
                "phone": user.phone,
                "dingtalk_id": user.dingtalk_id,
                "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
                "created_at": user.created_at.isoformat(),
            }
        )
    return data


async def _active_admin_count(db: AsyncSession, user_id_expr=None) -> int:
    """启用状态的管理员人数（可选地按 user_id 表达式过滤）。"""
    query = (
        select(func.count(func.distinct(UserRole.user_id)))
        .select_from(UserRole)
        .join(User, User.id == UserRole.user_id)
        .where(UserRole.role == BusinessRole.ADMIN.value, User.is_active == True)  # noqa: E712
    )
    if user_id_expr is not None:
        query = query.where(UserRole.user_id == user_id_expr)
    return (await db.execute(query)).scalar() or 0


def _sync_skill_groups(db: AsyncSession, user_id: int, memberships) -> None:
    """写入分系统关联（调用方负责先清空旧关联）。"""
    for membership in memberships:
        db.add(
            UserSkillGroup(
                user_id=user_id,
                skill_group_id=membership.skill_group_id,
                is_dispatcher=False,  # migration-only 列，POC 不再使用
            )
        )


@users_router.get("/users")
async def list_users(
    role: BusinessRole | None = None,
    skill_group_id: int | None = None,
    keyword: str | None = None,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """人员列表。

    - 管理员：返回完整字段，可按任意角色筛选。
    - 其他人：只返回流程需要的最小字段（id/name/roles/skill_groups），
      用于选择批准人和分系统负责人；拥有管理员角色的账号不出现在业务人员列表中。
    - `role=x` 的含义是「拥有角色 x 的用户」（多角色）。
    """
    is_admin = user.has_role(BusinessRole.ADMIN)

    query = select(User)
    if not include_inactive or not is_admin:
        query = query.where(User.is_active == True)  # noqa: E712
    if not is_admin:
        # 业务人员选择器不展示隐藏管理员
        query = query.where(
            ~User.id.in_(
                select(UserRole.user_id).where(UserRole.role == BusinessRole.ADMIN.value)
            )
        )
    if role is not None:
        query = query.where(
            User.id.in_(select(UserRole.user_id).where(UserRole.role == role.value))
        )
    if skill_group_id is not None:
        query = query.join(
            UserSkillGroup, UserSkillGroup.user_id == User.id
        ).where(UserSkillGroup.skill_group_id == skill_group_id)
    if keyword:
        query = query.where(
            or_(User.name.ilike(f"%{keyword}%"), User.username.ilike(f"%{keyword}%"))
        )

    users = (await db.execute(query.order_by(User.id))).scalars().unique().all()
    return {"data": [_user_payload(u, full=is_admin) for u in users]}


@users_router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ADMIN_ONLY),
):
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail="用户名已存在")

    new_user = User(
        username=body.username,
        name=body.name,
        phone=body.phone,
        password_hash=hash_password(body.password),
        dingtalk_id=body.dingtalk_id,
    )
    # 角色必须在 flush 前设置：新建对象尚未持久化，集合为空不会触发懒加载，
    # flush 之后再访问未加载的集合会在异步会话里抛 MissingGreenlet。
    new_user.set_roles([role.value for role in body.roles])
    db.add(new_user)
    await db.flush()

    if new_user.has_role(BusinessRole.SUBSYSTEM):
        _sync_skill_groups(db, new_user.id, body.skill_groups)

    await db.commit()
    return {
        "data": {
            "id": new_user.id,
            "username": new_user.username,
            "roles": new_user.roles,
        }
    }


@users_router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ADMIN_ONLY),
):
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None:
        raise NotFoundError("用户", user_id)

    new_roles = [role.value for role in body.roles] if body.roles is not None else None
    if (
        new_roles is not None
        and target.has_role(BusinessRole.ADMIN)
        and BusinessRole.ADMIN.value not in new_roles
    ):
        if await _active_admin_count(db, target.id) <= 1:
            raise HTTPException(400, detail="不能移除最后一个管理员的 admin 角色")

    if body.name is not None:
        target.name = body.name
    if body.phone is not None:
        target.phone = body.phone
    if body.password:
        target.password_hash = hash_password(body.password)
    if body.dingtalk_id is not None:
        target.dingtalk_id = body.dingtalk_id
    if body.is_active is not None:
        target.is_active = body.is_active
    if new_roles is not None:
        target.set_roles(new_roles)

    # 分系统关联：只有拥有 subsystem 角色的用户才保留
    has_subsystem = target.has_role(BusinessRole.SUBSYSTEM) if new_roles is None else (
        BusinessRole.SUBSYSTEM.value in new_roles
    )
    if body.skill_groups is not None or new_roles is not None:
        await db.execute(
            UserSkillGroup.__table__.delete().where(UserSkillGroup.user_id == user_id)
        )
        if has_subsystem:
            _sync_skill_groups(db, user_id, body.skill_groups or [])

    await db.commit()
    return {
        "data": {
            "id": target.id,
            "username": target.username,
            "roles": target.roles,
        }
    }


@users_router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ADMIN_ONLY),
):
    target = await db.get(User, user_id)
    if target is None:
        raise NotFoundError("用户", user_id)
    target.is_active = True
    await db.commit()
    return {"data": {"id": target.id, "is_active": True}}


@users_router.delete("/users/{user_id}")
async def deactivate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ADMIN_ONLY),
):
    target = await db.get(User, user_id)
    if target is None:
        raise NotFoundError("用户", user_id)
    if target.has_role(BusinessRole.ADMIN) and target.is_active:
        if await _active_admin_count(db, target.id) <= 1:
            raise HTTPException(400, detail="不能禁用最后一个管理员")
    target.is_active = False
    await db.commit()
    return {"data": {"id": target.id, "is_active": False}}


# ── Skill Groups（分系统）──────────────────────────────────

skill_groups_router = APIRouter(tags=["skill-groups"])


@skill_groups_router.get("/skill-groups")
async def list_skill_groups(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    groups = (await db.execute(select(SkillGroup).order_by(SkillGroup.id))).scalars().all()
    return {
        "data": [
            {
                "id": g.id,
                "name": g.name,
                "dingtalk_webhook_url": g.dingtalk_webhook_url,
                "created_at": g.created_at.isoformat(),
            }
            for g in groups
        ]
    }


def _gone(name: str):
    raise HTTPException(
        status.HTTP_410_GONE,
        detail=f"接口 {name} 属于旧客服流程，已下线；请使用分系统与角色人员接口",
    )


@skill_groups_router.get(
    "/skill-groups/{group_id}/dispatchers", include_in_schema=False
)
async def list_dispatchers(group_id: int, user: User = Depends(get_current_user)):
    _gone("部门对接人列表")


@skill_groups_router.get(
    "/skill-groups/{group_id}/handlers", include_in_schema=False
)
async def list_handlers(group_id: int, user: User = Depends(get_current_user)):
    _gone("处理人列表")


@skill_groups_router.post("/skill-groups", status_code=status.HTTP_201_CREATED)
async def create_skill_group(
    body: SkillGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ADMIN_ONLY),
):
    group = SkillGroup(name=body.name, dingtalk_webhook_url=body.dingtalk_webhook_url)
    db.add(group)
    await db.commit()
    return {"data": {"id": group.id, "name": group.name}}


@skill_groups_router.patch("/skill-groups/{group_id}")
async def update_skill_group(
    group_id: int,
    body: SkillGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ADMIN_ONLY),
):
    group = await db.get(SkillGroup, group_id)
    if group is None:
        raise NotFoundError("分系统", group_id)
    group.name = body.name
    group.dingtalk_webhook_url = body.dingtalk_webhook_url
    await db.commit()
    return {"data": {"id": group.id, "name": group.name}}


@skill_groups_router.post("/skill-groups/{group_id}/test-dingtalk")
async def test_skill_group_dingtalk(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ADMIN_ONLY),
):
    group = await db.get(SkillGroup, group_id)
    if group is None:
        raise NotFoundError("分系统", group_id)
    if not group.dingtalk_webhook_url:
        raise HTTPException(422, detail="请先配置并保存钉钉 Webhook")
    result = await send_dingtalk_text(
        group.dingtalk_webhook_url,
        f"【POC 质量问题闭环】分系统「{group.name}」机器人连接测试成功",
    )
    if not result.success:
        raise HTTPException(502, detail=result.error_message)
    return {"data": {"success": True}}


@skill_groups_router.delete("/skill-groups/{group_id}")
async def delete_skill_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(ADMIN_ONLY),
):
    group = await db.get(SkillGroup, group_id)
    if group is None:
        raise NotFoundError("分系统", group_id)
    member_count = (
        await db.execute(
            select(func.count())
            .select_from(UserSkillGroup)
            .where(UserSkillGroup.skill_group_id == group_id)
        )
    ).scalar() or 0
    if member_count > 0:
        raise HTTPException(400, detail=f"该分系统下还有 {member_count} 个用户，无法删除")
    ticket_count = (
        await db.execute(
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.skill_group_id == group_id, Ticket.legacy_state.is_(None))
        )
    ).scalar() or 0
    if ticket_count > 0:
        raise HTTPException(400, detail=f"该分系统还有 {ticket_count} 个关联问题，无法删除")
    await db.delete(group)
    await db.commit()
    return {"data": {"id": group_id, "deleted": True}}


# ── 枚举元数据（供前端对齐契约）────────────────────────────

meta_router = APIRouter(tags=["meta"])


@meta_router.get("/meta/poc-workflow")
async def poc_workflow_meta(user: User = Depends(get_current_user)):
    """POC 流程固定枚举。前端只从这里（或 OpenAPI）取编码，不得自行发明。"""
    return {
        "data": {
            "business_roles": [role.value for role in ALL_ROLES],
            "selectable_roles": [
                role.value for role in ALL_ROLES if role is not BusinessRole.ADMIN
            ],
            "states": [state.value for state in STATE_ORDER],
            "actions": [action.value for action in TicketAction],
            "priorities": [priority.value for priority in Priority],
            "verification_statuses": [
                status_.value for status_ in VerificationStatus
            ],
            "terminal_states": [state.value for state in (TicketState.CLOSED, TicketState.CANCELLED)],
        }
    }


# ── POC 统计 ───────────────────────────────────────────────

stats_router = APIRouter(tags=["stats"])


def _scoped_conditions(user: User):
    conditions = [Ticket.legacy_state.is_(None), Ticket.is_draft == False]  # noqa: E712
    scope = ticket_scope(user)
    return conditions + ([scope] if scope is not None else [])


async def _count(db: AsyncSession, conditions) -> int:
    return (
        await db.execute(select(func.count()).select_from(Ticket).where(*conditions))
    ).scalar() or 0


@stats_router.get("/stats/dashboard")
async def dashboard_stats(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    base = _scoped_conditions(user)
    now = datetime.now(timezone.utc)
    today = now.date()

    total = await _count(db, base)
    open_count = await _count(db, base + [Ticket.state.notin_(TERMINAL_VALUES)])
    closed_count = await _count(db, base + [Ticket.state == TicketState.CLOSED.value])
    overdue_count = await _count(
        db,
        base
        + [
            Ticket.planned_completion_at.is_not(None),
            Ticket.planned_completion_at < now,
            Ticket.state.notin_(TERMINAL_VALUES),
        ],
    )
    today_created = await _count(db, base + [func.date(Ticket.created_at) == today])
    today_closed = await _count(
        db, base + [Ticket.state == TicketState.CLOSED.value, func.date(Ticket.closed_at) == today]
    )

    async def grouped(column):
        rows = (
            await db.execute(select(column, func.count(Ticket.id)).where(*base).group_by(column))
        ).all()
        return {str(key): count for key, count in rows if key is not None}

    rows = (
        await db.execute(
            select(SkillGroup.name, func.count(Ticket.id))
            .select_from(Ticket)
            .join(SkillGroup, SkillGroup.id == Ticket.skill_group_id)
            .where(*base)
            .group_by(SkillGroup.name)
        )
    ).all()

    return {
        "data": {
            "total": total,
            "open_count": open_count,
            "closed_count": closed_count,
            "overdue_count": overdue_count,
            "today_created": today_created,
            "today_closed": today_closed,
            "pending_approval_count": await _count(
                db, base + [Ticket.state == TicketState.PENDING_APPROVAL.value]
            ),
            "planning_count": await _count(
                db,
                base
                + [
                    Ticket.state.in_(
                        [
                            TicketState.PLANNING.value,
                            TicketState.PENDING_PLAN_CONFIRMATION.value,
                            TicketState.PROCESSING.value,
                        ]
                    )
                ],
            ),
            "by_state": await grouped(Ticket.state),
            "by_priority": await grouped(Ticket.priority),
            "by_skill_group": {name: count for name, count in rows},
            "by_verification_status": await grouped(Ticket.verification_status),
        }
    }


@stats_router.get("/stats/report")
async def report_stats(
    period: str = Query("daily", pattern="^(daily|weekly|monthly|quarterly|custom)$"),
    date_from: str | None = None,
    date_to: str | None = None,
    skill_group_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """POC 问题闭环统计（新增量 / 闭环量 / 逾期率 / 验证状态分布）。"""
    today = date.today()
    if not date_from or not date_to:
        if period == "daily":
            date_from = date_to = today.isoformat()
        elif period == "weekly":
            monday = today - timedelta(days=today.weekday())
            date_from, date_to = monday.isoformat(), (monday + timedelta(days=6)).isoformat()
        elif period == "monthly":
            date_from, date_to = today.replace(day=1).isoformat(), today.isoformat()
        elif period == "quarterly":
            q_start = ((today.month - 1) // 3) * 3 + 1
            date_from, date_to = today.replace(month=q_start, day=1).isoformat(), today.isoformat()
        else:
            date_from = date_to = today.isoformat()

    try:
        start_date = date.fromisoformat(date_from)
        end_date = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(422, detail="date_from/date_to 格式错误，应为 YYYY-MM-DD")
    if end_date < start_date:
        raise HTTPException(422, detail="date_to 不能早于 date_from")

    start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    base = _scoped_conditions(user)
    if skill_group_id:
        base = base + [Ticket.skill_group_id == skill_group_id]

    span = (end_date - start_date).days + 1

    async def window(window_start: datetime, window_end: datetime) -> dict:
        created = await _count(
            db, base + [Ticket.created_at >= window_start, Ticket.created_at <= window_end]
        )
        closed = await _count(
            db,
            base
            + [
                Ticket.state == TicketState.CLOSED.value,
                Ticket.closed_at.is_not(None),
                Ticket.closed_at >= window_start,
                Ticket.closed_at <= window_end,
            ],
        )
        overdue = await _count(
            db,
            base
            + [
                Ticket.planned_completion_at.is_not(None),
                Ticket.planned_completion_at < window_end,
                Ticket.created_at >= window_start,
                Ticket.created_at <= window_end,
            ],
        )
        return {"new_count": created, "closed_count": closed, "overdue_count": overdue}

    metrics = await window(start, end)
    metrics["overdue_rate"] = (
        round(metrics["overdue_count"] / metrics["new_count"], 4)
        if metrics["new_count"]
        else 0.0
    )
    metrics["closure_rate"] = (
        round(metrics["closed_count"] / metrics["new_count"], 4)
        if metrics["new_count"]
        else 0.0
    )

    # 平均闭环时长（本窗口闭环的问题）
    avg_minutes = (
        await db.execute(
            select(
                func.avg(
                    func.extract("epoch", Ticket.closed_at - Ticket.created_at) / 60.0
                )
            ).where(
                *base,
                Ticket.state == TicketState.CLOSED.value,
                Ticket.closed_at.is_not(None),
                Ticket.closed_at >= start,
                Ticket.closed_at <= end,
            )
        )
    ).scalar()

    prev_end_date = start_date - timedelta(days=1)
    prev_start_date = prev_end_date - timedelta(days=span - 1)
    prev_metrics = await window(
        datetime.combine(prev_start_date, datetime.min.time()).replace(tzinfo=timezone.utc),
        datetime.combine(prev_end_date, datetime.max.time()).replace(tzinfo=timezone.utc),
    )

    def grouped(column):
        return select(column, func.count(Ticket.id)).where(*base).group_by(column)

    async def group_map(column):
        rows = (await db.execute(grouped(column))).all()
        return {str(k): v for k, v in rows if k is not None}

    group_rows = (
        await db.execute(
            select(SkillGroup.name, func.count(Ticket.id))
            .select_from(Ticket)
            .join(SkillGroup, SkillGroup.id == Ticket.skill_group_id)
            .where(*base)
            .group_by(SkillGroup.name)
        )
    ).all()

    return {
        "data": {
            "period": period,
            "date_from": date_from,
            "date_to": date_to,
            "metrics": {
                **metrics,
                "avg_closure_minutes": int(avg_minutes) if avg_minutes else None,
                "by_verification_status": await group_map(Ticket.verification_status),
                "by_priority": await group_map(Ticket.priority),
                "by_skill_group": {name: count for name, count in group_rows},
            },
            "prev_metrics": prev_metrics,
        }
    }


@stats_router.get("/stats/trend")
async def trend_stats(
    date_from: str | None = None,
    date_to: str | None = None,
    skill_group_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """按天返回新增 / 闭环 / 逾期趋势。"""
    today = date.today()
    if not date_from or not date_to:
        date_from = (today - timedelta(days=13)).isoformat()
        date_to = today.isoformat()
    try:
        start_date = date.fromisoformat(date_from)
        end_date = date.fromisoformat(date_to)
    except ValueError:
        raise HTTPException(422, detail="date_from/date_to 格式错误，应为 YYYY-MM-DD")

    start = datetime.combine(start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    end = datetime.combine(end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    base = _scoped_conditions(user)
    if skill_group_id:
        base = base + [Ticket.skill_group_id == skill_group_id]

    new_rows = (
        await db.execute(
            select(func.date(Ticket.created_at), func.count(Ticket.id))
            .where(*base, Ticket.created_at >= start, Ticket.created_at <= end)
            .group_by(func.date(Ticket.created_at))
        )
    ).all()
    closed_rows = (
        await db.execute(
            select(func.date(Ticket.closed_at), func.count(Ticket.id)).where(
                *base,
                Ticket.state == TicketState.CLOSED.value,
                Ticket.closed_at.is_not(None),
                Ticket.closed_at >= start,
                Ticket.closed_at <= end,
            ).group_by(func.date(Ticket.closed_at))
        )
    ).all()
    overdue_rows = (
        await db.execute(
            select(func.date(Ticket.created_at), func.count(Ticket.id)).where(
                *base,
                Ticket.created_at >= start,
                Ticket.created_at <= end,
                Ticket.planned_completion_at.is_not(None),
                Ticket.planned_completion_at < end,
            ).group_by(func.date(Ticket.created_at))
        )
    ).all()

    new_map = {str(k): v for k, v in new_rows}
    closed_map = {str(k): v for k, v in closed_rows}
    overdue_map = {str(k): v for k, v in overdue_rows}

    days = []
    cursor = start_date
    while cursor <= end_date:
        key = cursor.isoformat()
        days.append(
            {
                "date": key,
                "new": new_map.get(key, 0),
                "closed": closed_map.get(key, 0),
                "overdue": overdue_map.get(key, 0),
            }
        )
        cursor += timedelta(days=1)

    return {"data": {"date_from": date_from, "date_to": date_to, "days": days}}
