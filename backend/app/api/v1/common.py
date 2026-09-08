"""Users, Groups, SkillGroups, Categories, Regions, SLA, Stats routers."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.exceptions import NotFoundError
from app.core.security import hash_password
from app.models.category import TicketCategory, Region
from app.models.group import Group, SkillGroup, UserSkillGroup
from app.models.sla import SLAPolicy
from app.models.ticket import Ticket, TicketStateLog
from app.models.user import User
from app.schemas.common import (
    CategoryCreate, CategoryOut, CategoryUpdate, DashboardStats, GroupCreate,
    GroupOut, RegionCreate, RegionOut, SLAPolicyCreate, SLAPolicyOut,
    SkillGroupCreate, SkillGroupOut, UserCreate, UserOut, UserUpdate,
)
from app.services.notification import send_dingtalk_text

# ── Users ─────────────────────────────────────────────────

users_router = APIRouter(tags=["users"])


@users_router.get("/users")
async def list_users(
    role: str | None = None,
    group_id: int | None = None,
    skill_group_id: int | None = None,
    keyword: str | None = None,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(User)
    # 默认只看启用用户；管理后台传 include_inactive=true 看全部
    show_all = include_inactive is True or str(include_inactive).lower() == "true"
    if not show_all:
        query = query.where(User.is_active == True)
    # 非管理员只能看到本组成员（用于选负责人/筛选）
    if user.role != "admin":
        query = query.where(User.group_id == user.group_id)
    if role:
        query = query.where(User.role == role)
    if group_id:
        query = query.where(User.group_id == group_id)
    if skill_group_id:
        # 按对接部门筛选：join user_skill_groups
        query = query.join(UserSkillGroup, UserSkillGroup.user_id == User.id).where(
            UserSkillGroup.skill_group_id == skill_group_id
        )
    if keyword:
        query = query.where(User.name.ilike(f"%{keyword}%") | User.username.ilike(f"%{keyword}%"))
    result = await db.execute(query.order_by(User.id))
    users = result.scalars().all()

    # 一次性查出所有用户的对接部门，避免 N+1
    user_ids = [u.id for u in users]
    skill_groups_map: dict[int, list[dict]] = {}
    if user_ids:
        sg_result = await db.execute(
            select(UserSkillGroup.user_id, UserSkillGroup.skill_group_id, UserSkillGroup.is_dispatcher)
            .where(UserSkillGroup.user_id.in_(user_ids))
        )
        for uid, sgid, is_disp in sg_result.all():
            skill_groups_map.setdefault(uid, []).append({
                "skill_group_id": sgid,
                "is_dispatcher": is_disp,
            })

    data = []
    for u in users:
        data.append({
            "id": u.id, "username": u.username, "name": u.name, "phone": u.phone,
            "role": u.role, "group_id": u.group_id, "is_group_leader": u.is_group_leader,
            "is_active": u.is_active, "dingtalk_id": u.dingtalk_id,
            "skill_groups": skill_groups_map.get(u.id, []),
            "created_at": u.created_at.isoformat(),
        })
    return {"data": data}


@users_router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_user(
    body: UserCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    # Check duplicate username
    existing = await db.execute(select(User).where(User.username == body.username))
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail="用户名已存在")

    u = User(
        username=body.username, name=body.name, phone=body.phone,
        password_hash=hash_password(body.password), role=body.role,
        group_id=body.group_id, is_group_leader=body.is_group_leader,
        dingtalk_id=body.dingtalk_id,
    )
    db.add(u)
    await db.flush()
    # Add skill groups（对接部门，含对接人标记）
    from app.models.group import UserSkillGroup
    for m in body.skill_groups:
        db.add(UserSkillGroup(user_id=u.id, skill_group_id=m.skill_group_id, is_dispatcher=m.is_dispatcher))
    await db.flush()
    return {"data": {"id": u.id, "username": u.username, "name": u.name, "role": u.role}}


@users_router.patch("/users/{user_id}")
async def update_user(
    user_id: int,
    body: UserUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """编辑用户信息。密码为空则不改。"""
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise NotFoundError("用户", user_id)

    # 不能禁用/降级最后一个管理员
    if body.role is not None and body.role != "admin" and u.role == "admin":
        admin_count = (await db.execute(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active == True)
        )).scalar() or 0
        if admin_count <= 1:
            raise HTTPException(400, detail="不能降级最后一个管理员")

    if body.name is not None:
        u.name = body.name
    if body.phone is not None:
        u.phone = body.phone
    if body.password:
        u.password_hash = hash_password(body.password)
    if body.role is not None:
        u.role = body.role
    if body.group_id is not None:
        u.group_id = body.group_id
    if body.is_group_leader is not None:
        u.is_group_leader = body.is_group_leader
    if body.dingtalk_id is not None:
        u.dingtalk_id = body.dingtalk_id
    if body.is_active is not None:
        u.is_active = body.is_active

    # 更新对接部门关联（全量替换，含对接人标记）
    if body.skill_groups is not None:
        from app.models.group import UserSkillGroup
        await db.execute(
            UserSkillGroup.__table__.delete().where(UserSkillGroup.user_id == user_id)
        )
        for m in body.skill_groups:
            db.add(UserSkillGroup(user_id=user_id, skill_group_id=m.skill_group_id, is_dispatcher=m.is_dispatcher))

    await db.flush()
    return {"data": {"id": u.id, "username": u.username, "name": u.name, "role": u.role}}


@users_router.post("/users/{user_id}/activate")
async def activate_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """启用用户。"""
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise NotFoundError("用户", user_id)
    u.is_active = True
    return {"data": {"id": u.id, "is_active": True}}


@users_router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """禁用用户（软删除）。"""
    result = await db.execute(select(User).where(User.id == user_id))
    u = result.scalar_one_or_none()
    if not u:
        raise NotFoundError("用户", user_id)
    # 不能禁用最后一个管理员
    if u.role == "admin" and u.is_active:
        admin_count = (await db.execute(
            select(func.count()).select_from(User).where(User.role == "admin", User.is_active == True)
        )).scalar() or 0
        if admin_count <= 1:
            raise HTTPException(400, detail="不能禁用最后一个管理员")
    u.is_active = False
    return {"data": {"id": u.id, "is_active": False}}


# ── Groups ────────────────────────────────────────────────

groups_router = APIRouter(tags=["groups"])


@groups_router.get("/groups")
async def list_groups(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(Group).order_by(Group.id))
    groups = result.scalars().all()
    return {"data": [{"id": g.id, "name": g.name, "dingtalk_webhook_url": g.dingtalk_webhook_url, "created_at": g.created_at.isoformat()} for g in groups]}


@groups_router.post("/groups", status_code=status.HTTP_201_CREATED)
async def create_group(body: GroupCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role("admin"))):
    g = Group(name=body.name, dingtalk_webhook_url=body.dingtalk_webhook_url)
    db.add(g)
    await db.flush()
    return {"data": {"id": g.id, "name": g.name}}


@groups_router.patch("/groups/{group_id}")
async def update_group(
    group_id: int,
    body: GroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(Group).where(Group.id == group_id))
    g = result.scalar_one_or_none()
    if not g:
        raise NotFoundError("客服组", group_id)
    g.name = body.name
    g.dingtalk_webhook_url = body.dingtalk_webhook_url
    await db.flush()
    return {"data": {"id": g.id, "name": g.name}}


@groups_router.post("/groups/{group_id}/test-dingtalk")
async def test_group_dingtalk(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(Group).where(Group.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise NotFoundError("客服组", group_id)
    if not group.dingtalk_webhook_url:
        raise HTTPException(422, detail="请先配置并保存钉钉 Webhook")
    send_result = await send_dingtalk_text(
        group.dingtalk_webhook_url,
        f"【客服工单系统】客服组「{group.name}」机器人连接测试成功",
    )
    if not send_result.success:
        raise HTTPException(502, detail=send_result.error_message)
    return {"data": {"success": True}}


@groups_router.delete("/groups/{group_id}")
async def delete_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(Group).where(Group.id == group_id))
    g = result.scalar_one_or_none()
    if not g:
        raise NotFoundError("客服组", group_id)
    # 校验：有用户或工单关联则拒绝
    user_count = (await db.execute(
        select(func.count()).select_from(User).where(User.group_id == group_id)
    )).scalar() or 0
    if user_count > 0:
        raise HTTPException(400, detail=f"该客服组下还有 {user_count} 个用户，无法删除")
    ticket_count = (await db.execute(
        select(func.count()).select_from(Ticket).where(Ticket.group_id == group_id)
    )).scalar() or 0
    if ticket_count > 0:
        raise HTTPException(400, detail=f"该客服组还有 {ticket_count} 个关联工单，无法删除")
    await db.delete(g)
    return {"data": {"id": group_id, "deleted": True}}


# ── Skill Groups ──────────────────────────────────────────

skill_groups_router = APIRouter(tags=["skill-groups"])


@skill_groups_router.get("/skill-groups")
async def list_skill_groups(db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    result = await db.execute(select(SkillGroup).order_by(SkillGroup.id))
    groups = result.scalars().all()
    return {"data": [{"id": g.id, "name": g.name, "dingtalk_webhook_url": g.dingtalk_webhook_url, "created_at": g.created_at.isoformat()} for g in groups]}


@skill_groups_router.get("/skill-groups/{group_id}/dispatchers")
async def list_dispatchers(group_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """获取某对接部门的部门对接人列表（建单时选对接人用）。"""
    from app.models.group import UserSkillGroup
    result = await db.execute(
        select(User).join(UserSkillGroup, UserSkillGroup.user_id == User.id).where(
            UserSkillGroup.skill_group_id == group_id,
            UserSkillGroup.is_dispatcher == True,
            User.is_active == True,
        ).order_by(User.id)
    )
    users = result.scalars().all()
    return {"data": [{"id": u.id, "name": u.name, "username": u.username} for u in users]}


@skill_groups_router.get("/skill-groups/{group_id}/handlers")
async def list_handlers(group_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """获取某对接部门的处理人列表（分派时选处理人用），部门对接人也可作为处理人。"""
    from app.models.group import UserSkillGroup
    result = await db.execute(
        select(User).join(UserSkillGroup, UserSkillGroup.user_id == User.id).where(
            UserSkillGroup.skill_group_id == group_id,
            User.is_active == True,
        ).order_by(User.id)
    )
    users = result.scalars().all()
    return {"data": [{"id": u.id, "name": u.name, "username": u.username} for u in users]}


@skill_groups_router.post("/skill-groups", status_code=status.HTTP_201_CREATED)
async def create_skill_group(body: SkillGroupCreate, db: AsyncSession = Depends(get_db), user: User = Depends(require_role("admin"))):
    g = SkillGroup(name=body.name, dingtalk_webhook_url=body.dingtalk_webhook_url)
    db.add(g)
    await db.flush()
    return {"data": {"id": g.id, "name": g.name}}


@skill_groups_router.patch("/skill-groups/{group_id}")
async def update_skill_group(
    group_id: int,
    body: SkillGroupCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(SkillGroup).where(SkillGroup.id == group_id))
    g = result.scalar_one_or_none()
    if not g:
        raise NotFoundError("对接部门", group_id)
    g.name = body.name
    g.dingtalk_webhook_url = body.dingtalk_webhook_url
    await db.flush()
    return {"data": {"id": g.id, "name": g.name}}


@skill_groups_router.post("/skill-groups/{group_id}/test-dingtalk")
async def test_skill_group_dingtalk(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(SkillGroup).where(SkillGroup.id == group_id))
    group = result.scalar_one_or_none()
    if not group:
        raise NotFoundError("对接部门", group_id)
    if not group.dingtalk_webhook_url:
        raise HTTPException(422, detail="请先配置并保存钉钉 Webhook")
    send_result = await send_dingtalk_text(
        group.dingtalk_webhook_url,
        f"【客服工单系统】对接部门「{group.name}」机器人连接测试成功",
    )
    if not send_result.success:
        raise HTTPException(502, detail=send_result.error_message)
    return {"data": {"success": True}}


@skill_groups_router.delete("/skill-groups/{group_id}")
async def delete_skill_group(
    group_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    from app.models.group import UserSkillGroup
    result = await db.execute(select(SkillGroup).where(SkillGroup.id == group_id))
    g = result.scalar_one_or_none()
    if not g:
        raise NotFoundError("对接部门", group_id)
    # 校验：有用户关联则拒绝
    user_count = (await db.execute(
        select(func.count()).select_from(UserSkillGroup).where(UserSkillGroup.skill_group_id == group_id)
    )).scalar() or 0
    if user_count > 0:
        raise HTTPException(400, detail=f"该对接部门下还有 {user_count} 个用户，无法删除")
    # 校验：有工单关联则拒绝
    ticket_count = (await db.execute(
        select(func.count()).select_from(Ticket).where(Ticket.skill_group_id == group_id)
    )).scalar() or 0
    if ticket_count > 0:
        raise HTTPException(400, detail=f"该对接部门还有 {ticket_count} 个关联工单，无法删除")
    await db.delete(g)
    return {"data": {"id": group_id, "deleted": True}}


# ── Categories ────────────────────────────────────────────

categories_router = APIRouter(tags=["categories"])


@categories_router.get("/categories")
async def list_categories(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(TicketCategory)
    show_all = include_inactive is True or str(include_inactive).lower() == "true"
    if not show_all:
        query = query.where(TicketCategory.is_active == True)
    result = await db.execute(query.order_by(TicketCategory.sort_order, TicketCategory.id))
    all_cats = result.scalars().all()

    # Build tree
    by_id = {c.id: {"id": c.id, "name": c.name, "level": c.level, "parent_id": c.parent_id, "sort_order": c.sort_order, "children": []} for c in all_cats}
    tree = []
    for c in all_cats:
        node = by_id[c.id]
        if c.parent_id and c.parent_id in by_id:
            by_id[c.parent_id]["children"].append(node)
        else:
            tree.append(node)
    return {"data": tree}


@categories_router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    level = 1
    if body.parent_id is not None:
        parent = await db.execute(select(TicketCategory).where(TicketCategory.id == body.parent_id))
        parent_cat = parent.scalar_one_or_none()
        if not parent_cat:
            raise HTTPException(400, detail="父级分类不存在")
        if parent_cat.level != 1:
            raise HTTPException(400, detail="二级分类不能作为父级")
        level = 2

    # 同级名称去重
    dup_cond = [
        TicketCategory.name == body.name,
        TicketCategory.level == level,
        TicketCategory.parent_id == body.parent_id,
    ]
    existing = await db.execute(select(TicketCategory).where(*dup_cond))
    if existing.scalar_one_or_none():
        raise HTTPException(400, detail="同级下已存在同名分类")

    cat = TicketCategory(
        name=body.name,
        parent_id=body.parent_id,
        level=level,
        sort_order=body.sort_order,
        is_active=body.is_active,
    )
    db.add(cat)
    await db.flush()
    return {"data": {"id": cat.id, "name": cat.name, "level": cat.level, "parent_id": cat.parent_id, "sort_order": cat.sort_order}}


@categories_router.patch("/categories/{category_id}")
async def update_category(
    category_id: int,
    body: CategoryUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(TicketCategory).where(TicketCategory.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise NotFoundError("分类", category_id)

    new_name = body.name if body.name is not None else cat.name
    # 如果改名，校验同级同名
    if body.name is not None and body.name != cat.name:
        dup_cond = [
            TicketCategory.name == body.name,
            TicketCategory.level == cat.level,
            TicketCategory.parent_id == cat.parent_id,
            TicketCategory.id != category_id,
        ]
        existing = await db.execute(select(TicketCategory).where(*dup_cond))
        if existing.scalar_one_or_none():
            raise HTTPException(400, detail="同级下已存在同名分类")
        cat.name = body.name

    if body.sort_order is not None:
        cat.sort_order = body.sort_order
    if body.is_active is not None:
        cat.is_active = body.is_active

    await db.flush()
    return {"data": {"id": cat.id, "name": cat.name, "level": cat.level, "parent_id": cat.parent_id, "sort_order": cat.sort_order, "is_active": cat.is_active}}


@categories_router.delete("/categories/{category_id}")
async def delete_category(
    category_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(TicketCategory).where(TicketCategory.id == category_id))
    cat = result.scalar_one_or_none()
    if not cat:
        raise NotFoundError("分类", category_id)

    # 一级分类下若有二级分类，先要求删除子分类
    if cat.level == 1:
        child_count = (await db.execute(
            select(func.count()).select_from(TicketCategory).where(TicketCategory.parent_id == category_id)
        )).scalar() or 0
        if child_count > 0:
            raise HTTPException(400, detail=f"该分类下还有 {child_count} 个子分类，请先删除子分类")

    # 有关联工单则拒绝
    ticket_count = (await db.execute(
        select(func.count()).select_from(Ticket).where(Ticket.category_id == category_id)
    )).scalar() or 0
    if ticket_count > 0:
        raise HTTPException(400, detail=f"该分类还有 {ticket_count} 个关联工单，无法删除")

    await db.delete(cat)
    return {"data": {"id": category_id, "deleted": True}}


# ── Regions ───────────────────────────────────────────────

regions_router = APIRouter(tags=["regions"])


@regions_router.get("/regions")
async def list_regions(
    parent_id: int | None = None,
    level: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Region).where(Region.is_active == True)
    if parent_id is not None:
        query = query.where(Region.parent_id == parent_id)
    if level is not None:
        query = query.where(Region.level == level)
    query = query.order_by(Region.sort_order, Region.id)
    result = await db.execute(query)
    regions = result.scalars().all()
    return {"data": [{"id": r.id, "name": r.name, "level": r.level, "parent_id": r.parent_id, "code": r.code, "sort_order": r.sort_order} for r in regions]}


# ── SLA Policies ──────────────────────────────────────────

sla_router = APIRouter(tags=["sla"])


@sla_router.get("/sla-policies")
async def list_sla_policies(db: AsyncSession = Depends(get_db), user: User = Depends(require_role("admin"))):
    result = await db.execute(select(SLAPolicy).order_by(SLAPolicy.id))
    policies = result.scalars().all()
    data = []
    for p in policies:
        sg_name = None
        if p.skill_group_id:
            r = await db.execute(select(SkillGroup.name).where(SkillGroup.id == p.skill_group_id))
            sg_name = r.scalar_one_or_none()
        data.append({
            "id": p.id, "skill_group_id": p.skill_group_id, "skill_group_name": sg_name,
            "priority": p.priority,
            "solution_minutes": p.solution_minutes, "created_at": p.created_at.isoformat(),
        })
    return {"data": data}


@sla_router.post("/sla-policies", status_code=status.HTTP_201_CREATED)
async def create_sla_policy(
    body: SLAPolicyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """新增 SLA 策略。skill_group_id+priority 唯一，已存在则报错。"""
    existing = await db.execute(
        select(SLAPolicy).where(
            SLAPolicy.skill_group_id == body.skill_group_id,
            SLAPolicy.priority == body.priority,
        )
    )
    if existing.scalar_one_or_none():
        label = f"对接部门{body.skill_group_id}+" if body.skill_group_id else "全局默认+"
        raise HTTPException(409, detail=f"{label}{body.priority} 的策略已存在，请直接编辑")
    p = SLAPolicy(
        skill_group_id=body.skill_group_id, priority=body.priority,
        first_response_minutes=0,  # 已废弃，保留字段兼容旧数据
        solution_minutes=body.solution_minutes,
    )
    db.add(p)
    await db.flush()
    return {"data": {"id": p.id}}


@sla_router.patch("/sla-policies/{policy_id}")
async def update_sla_policy(
    policy_id: int,
    body: SLAPolicyCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(SLAPolicy).where(SLAPolicy.id == policy_id))
    p = result.scalar_one_or_none()
    if not p:
        raise NotFoundError("SLA策略", policy_id)
    p.skill_group_id = body.skill_group_id
    p.priority = body.priority
    p.solution_minutes = body.solution_minutes
    await db.flush()
    return {"data": {"id": p.id}}


@sla_router.delete("/sla-policies/{policy_id}")
async def delete_sla_policy(
    policy_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(SLAPolicy).where(SLAPolicy.id == policy_id))
    p = result.scalar_one_or_none()
    if not p:
        raise NotFoundError("SLA策略", policy_id)
    await db.delete(p)
    return {"data": {"id": policy_id, "deleted": True}}


# ── Stats ─────────────────────────────────────────────────

stats_router = APIRouter(tags=["stats"])


@stats_router.get("/stats/dashboard")
async def dashboard_stats(
    group_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    from datetime import datetime, timezone
    from sqlalchemy import or_
    today = datetime.now(timezone.utc).date()

    # 按角色限定统计范围（与工单列表 list_tickets 保持一致）
    scope_conditions = []
    if user.role == "handler":
        scope_conditions.append(Ticket.owner_id == user.id)
    elif user.role == "agent":
        if not user.is_group_leader:
            # 普通坐席：自己受理的 + 本组的
            scope_conditions.append(or_(
                Ticket.owner_id == user.id,
                Ticket.group_id == user.group_id,
            ))
        # 组长：本组全部（不加条件，下面按 group_id 过滤）
    # admin：全部

    # 组长/admin 可指定 group_id；普通坐席强制限定为自己的组
    if user.role == "agent" and not user.is_group_leader:
        scope_conditions.append(Ticket.group_id == user.group_id)
    elif group_id:
        scope_conditions.append(Ticket.group_id == group_id)

    def scoped(*extra):
        """构造带 scope 过滤的 count 查询"""
        stmt = select(func.count()).select_from(Ticket)
        for cond in scope_conditions:
            stmt = stmt.where(cond)
        for cond in extra:
            stmt = stmt.where(cond)
        return stmt

    # Counts
    pending = (await db.execute(scoped(Ticket.state == "pending"))).scalar() or 0
    open_count = (await db.execute(scoped(Ticket.state == "open"))).scalar() or 0
    overdue = (await db.execute(scoped(
        Ticket.sla_solution_breached == True, Ticket.state.notin_(["archived", "cancelled"])
    ))).scalar() or 0
    today_created = (await db.execute(scoped(func.date(Ticket.created_at) == today))).scalar() or 0
    today_resolved = (await db.execute(scoped(
        Ticket.state == "resolved", func.date(Ticket.solved_at) == today
    ))).scalar() or 0

    # SLA breach rate：按已结案工单（archived/cancelled）统计
    total_closed = (await db.execute(scoped(Ticket.state.in_(["archived", "cancelled"])))).scalar() or 0
    total_breached = (await db.execute(scoped(
        Ticket.state.in_(["archived", "cancelled"]),
        Ticket.sla_solution_breached == True
    ))).scalar() or 0
    breach_rate = round(total_breached / total_closed, 4) if total_closed else 0.0

    # by_category：按一级分类名统计工单数
    # join ticket_categories（叶子）→ 其 parent（一级分类名）
    cat_alias = TicketCategory.__table__.alias("cat")
    parent_alias = TicketCategory.__table__.alias("parent")
    cat_query = (
        select(parent_alias.c.name, func.count(Ticket.id))
        .select_from(Ticket)
        .join(cat_alias, cat_alias.c.id == Ticket.category_id)
        .join(parent_alias, parent_alias.c.id == cat_alias.c.parent_id)
    )
    for cond in scope_conditions:
        cat_query = cat_query.where(cond)
    cat_query = cat_query.group_by(parent_alias.c.name)
    cat_rows = (await db.execute(cat_query)).all()
    by_category = {row[0]: row[1] for row in cat_rows} if cat_rows else {}

    # by_priority：按优先级统计当前工单数
    prio_q = select(Ticket.priority, func.count(Ticket.id))
    for cond in scope_conditions:
        prio_q = prio_q.where(cond)
    prio_q = prio_q.group_by(Ticket.priority)
    prio_rows = (await db.execute(prio_q)).all()
    by_priority = {row[0]: row[1] for row in prio_rows} if prio_rows else {}

    return {
        "data": {
            "pending_count": pending, "open_count": open_count, "overdue_count": overdue,
            "today_created": today_created, "today_resolved": today_resolved,
            "sla_breach_rate": breach_rate,
            "first_contact_resolution_rate": 0.0,  # TODO: calculate
            "avg_resolution_minutes": None,
            "by_priority": by_priority, "by_category": by_category,
        }
    }


@stats_router.get("/stats/report")
async def report_stats(
    period: str = Query("daily", pattern="^(daily|weekly|monthly|quarterly|custom)$"),
    date_from: str | None = None,
    date_to: str | None = None,
    skill_group_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    """按时间范围聚合统计报表。

    period: daily/weekly/monthly/quarterly（仅作标识，实际范围由 date_from/date_to 决定）
    date_from/date_to: YYYY-MM-DD，默认为本周期范围
    """
    from datetime import date, datetime, timedelta, timezone

    today = date.today()
    # 默认时间范围按 period 推算
    if not date_from or not date_to:
        if period == "daily":
            date_from = date_to = today.isoformat()
        elif period == "weekly":
            monday = today - timedelta(days=today.weekday())
            date_from = monday.isoformat()
            date_to = (monday + timedelta(days=6)).isoformat()
        elif period == "monthly":
            date_from = today.replace(day=1).isoformat()
            date_to = today.isoformat()
        else:  # quarterly
            q_start_month = ((today.month - 1) // 3) * 3 + 1
            date_from = today.replace(month=q_start_month, day=1).isoformat()
            date_to = today.isoformat()

    start = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc, hour=23, minute=59, second=59)

    # 基础过滤：时间范围内创建的工单
    base = [Ticket.created_at >= start, Ticket.created_at <= end]
    if skill_group_id:
        base.append(Ticket.skill_group_id == skill_group_id)

    # 1. 新增量
    new_count = (await db.execute(
        select(func.count()).select_from(Ticket).where(*base)
    )).scalar() or 0

    # 2. 闭环量（closed_at 在范围内）
    closed_count = (await db.execute(
        select(func.count()).select_from(Ticket).where(
            *base, Ticket.closed_at.is_not(None),
            Ticket.closed_at >= start, Ticket.closed_at <= end,
        )
    )).scalar() or 0

    # 3. 处理中量（当前 open）
    in_progress = (await db.execute(
        select(func.count()).select_from(Ticket).where(*base, Ticket.state == "open")
    )).scalar() or 0

    # 4. 各对接部门平均处理时长（已闭环工单）
    sg_alias = SkillGroup.__table__.alias("sg")
    avg_q = (
        select(sg_alias.c.name, func.avg(Ticket.closed_duration_minutes))
        .select_from(Ticket)
        .join(sg_alias, sg_alias.c.id == Ticket.skill_group_id)
        .where(*base, Ticket.closed_duration_minutes.is_not(None))
        .group_by(sg_alias.c.name)
    )
    avg_rows = (await db.execute(avg_q)).all()
    avg_resolution_per_group = [
        {"group_name": r[0], "minutes": int(r[1]) if r[1] else 0} for r in avg_rows
    ]

    # 5. 超时率
    breached = (await db.execute(
        select(func.count()).select_from(Ticket).where(
            *base,
            Ticket.sla_solution_breached == True
        )
    )).scalar() or 0
    sla_breach_rate = round(breached / new_count, 4) if new_count else 0.0

    # 6. 故障分类分布（一级分类）
    cat_alias = TicketCategory.__table__.alias("cat")
    parent_alias = TicketCategory.__table__.alias("parent")
    cat_q = (
        select(parent_alias.c.name, func.count(Ticket.id))
        .select_from(Ticket)
        .join(cat_alias, cat_alias.c.id == Ticket.category_id)
        .join(parent_alias, parent_alias.c.id == cat_alias.c.parent_id)
        .where(*base)
        .group_by(parent_alias.c.name)
    )
    cat_rows = (await db.execute(cat_q)).all()
    by_category = [{"name": r[0], "count": r[1]} for r in cat_rows]

    # 7. 待回访工单：已处理、需要回访、尚未回访
    pending_callback = (await db.execute(
        select(func.count()).select_from(Ticket).where(
            *base,
            Ticket.state == "resolved",
            Ticket.callback_required == True,
            Ticket.is_callbacked == False,
        )
    )).scalar() or 0

    # 8. 回访满意度分布
    sat_rows = (await db.execute(
        select(Ticket.satisfaction, func.count(Ticket.id))
        .where(*base, Ticket.is_callbacked == True, Ticket.satisfaction.is_not(None))
        .group_by(Ticket.satisfaction)
    )).all()
    satisfaction_map = {r[0]: r[1] for r in sat_rows}
    satisfaction_breakdown = {
        "satisfied": satisfaction_map.get("satisfied", 0),
        "average": satisfaction_map.get("average", 0),
        "dissatisfied": satisfaction_map.get("dissatisfied", 0),
        "unrated": satisfaction_map.get("unrated", 0),
    }

    # 9. 二级分类分布（按一级分类名分组），用于点击一级分类弹出二级环形图
    sub_q = (
        select(parent_alias.c.name.label("parent_name"), cat_alias.c.name, func.count(Ticket.id))
        .select_from(Ticket)
        .join(cat_alias, cat_alias.c.id == Ticket.category_id)
        .join(parent_alias, parent_alias.c.id == cat_alias.c.parent_id)
        .where(*base)
        .group_by(parent_alias.c.name, cat_alias.c.name)
        .order_by(parent_alias.c.name, func.count(Ticket.id).desc())
    )
    sub_rows = (await db.execute(sub_q)).all()
    by_subcategory: dict[str, list[dict]] = {}
    for parent_name, child_name, count in sub_rows:
        by_subcategory.setdefault(parent_name, []).append({"name": child_name, "count": count})

    # 10. 上一周期对比（用于 KPI 卡显示 "较上周 ±X%"）
    span_days = (end.date() - start.date()).days + 1
    prev_end_date = start.date() - timedelta(days=1)
    prev_start_date = prev_end_date - timedelta(days=span_days - 1)
    prev_start = datetime.combine(prev_start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    prev_end = datetime.combine(prev_end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    prev_base = [Ticket.created_at >= prev_start, Ticket.created_at <= prev_end]
    if skill_group_id:
        prev_base.append(Ticket.skill_group_id == skill_group_id)

    prev_new = (await db.execute(
        select(func.count()).select_from(Ticket).where(*prev_base)
    )).scalar() or 0
    prev_in_progress = (await db.execute(
        select(func.count()).select_from(Ticket).where(*prev_base, Ticket.state == "open")
    )).scalar() or 0
    prev_closed = (await db.execute(
        select(func.count()).select_from(Ticket).where(
            *prev_base, Ticket.closed_at.is_not(None),
            Ticket.closed_at >= prev_start, Ticket.closed_at <= prev_end,
        )
    )).scalar() or 0
    prev_pending_callback = (await db.execute(
        select(func.count()).select_from(Ticket).where(
            *prev_base, Ticket.state == "resolved",
            Ticket.callback_required == True, Ticket.is_callbacked == False,
        )
    )).scalar() or 0
    prev_breached = (await db.execute(
        select(func.count()).select_from(Ticket).where(*prev_base, Ticket.sla_solution_breached == True)
    )).scalar() or 0
    prev_sla_rate = round(prev_breached / prev_new, 4) if prev_new else 0.0

    prev_sat_rows = (await db.execute(
        select(Ticket.satisfaction, func.count(Ticket.id))
        .where(*prev_base, Ticket.is_callbacked == True, Ticket.satisfaction.is_not(None))
        .group_by(Ticket.satisfaction)
    )).all()
    prev_sat_map = {r[0]: r[1] for r in prev_sat_rows}
    prev_sat_total = sum(prev_sat_map.values())
    prev_sat_satisfied = prev_sat_map.get("satisfied", 0)
    prev_satisfaction_rate = round(prev_sat_satisfied / prev_sat_total, 4) if prev_sat_total else 0.0

    prev_metrics = {
        "new_count": prev_new,
        "in_progress_count": prev_in_progress,
        "closed_count": prev_closed,
        "pending_callback_count": prev_pending_callback,
        "sla_breach_rate": prev_sla_rate,
        "satisfaction_rate": prev_satisfaction_rate,
    }

    # 11. 每日 SLA 超时率（SLA 卡右侧迷你趋势）
    sla_daily_rows = (await db.execute(
        select(
            func.date(Ticket.created_at).label("d"),
            func.count(Ticket.id).label("total"),
            func.sum(case((Ticket.sla_solution_breached == True, 1), else_=0)).label("breached"),
        )
        .where(*base)
        .group_by("d").order_by("d")
    )).all()
    sla_daily_map = {str(r[0]): round((r[2] or 0) / r[1], 4) if r[1] else 0.0 for r in sla_daily_rows}

    # 12. 每日回访满意度（满意度卡右侧迷你趋势：当日回访的满意度均值=satisfied/total）
    sat_daily_rows = (await db.execute(
        select(
            func.date(Ticket.solved_at).label("d"),
            func.count(Ticket.id).label("total"),
            func.sum(case((Ticket.satisfaction == "satisfied", 1), else_=0)).label("satisfied"),
        )
        .where(*base, Ticket.is_callbacked == True, Ticket.satisfaction.is_not(None))
        .group_by("d").order_by("d")
    )).all()
    sat_daily_map = {str(r[0]): round(r[2] / r[1], 4) if (r[1] and r[1] > 0) else 0.0 for r in sat_daily_rows}

    # 13. 一级分类每日趋势（分类表右侧迷你折线）
    cat_trend_rows = (await db.execute(
        select(
            func.date(Ticket.created_at).label("d"),
            parent_alias.c.name,
            func.count(Ticket.id),
        )
        .select_from(Ticket)
        .join(cat_alias, cat_alias.c.id == Ticket.category_id)
        .join(parent_alias, parent_alias.c.id == cat_alias.c.parent_id)
        .where(*base)
        .group_by("d", parent_alias.c.name)
        .order_by("d")
    )).all()
    category_trend: dict[str, dict[str, int]] = {}
    for d, name, count in cat_trend_rows:
        category_trend.setdefault(name, {})[str(d)] = count

    # 14. 把日序列补齐成 0（前端按日期范围渲染）
    def fill_daily(mapping: dict[str, float]) -> list[dict]:
        out = []
        cur = start.date()
        end_d = end.date()
        while cur <= end_d:
            key = cur.isoformat()
            out.append({"date": key, "value": mapping.get(key, 0.0)})
            cur += timedelta(days=1)
        return out

    sla_daily = fill_daily(sla_daily_map)
    satisfaction_daily = fill_daily(sat_daily_map)

    # 一级分类趋势也补齐
    cat_total = sum(c["count"] for c in by_category) or 1
    by_category_with_pct = [
        {
            "name": c["name"],
            "count": c["count"],
            "percentage": round(c["count"] / cat_total * 100, 1),
            "trend": fill_daily({k: float(v) for k, v in category_trend.get(c["name"], {}).items()}),
        }
        for c in by_category
    ]
    by_category_with_pct.sort(key=lambda x: x["count"], reverse=True)

    # 满意度总览率（满足 / 总）
    satisfaction_total = (
        satisfaction_breakdown["satisfied"]
        + satisfaction_breakdown["average"]
        + satisfaction_breakdown["dissatisfied"]
        + satisfaction_breakdown["unrated"]
    )
    satisfaction_rate = (
        round(satisfaction_breakdown["satisfied"] / satisfaction_total, 4)
        if satisfaction_total else 0.0
    )

    return {
        "data": {
            "period": period,
            "date_from": date_from,
            "date_to": date_to,
            "metrics": {
                "new_count": new_count,
                "in_progress_count": in_progress,
                "closed_count": closed_count,
                "pending_callback_count": pending_callback,
                "satisfaction_breakdown": satisfaction_breakdown,
                "satisfaction_rate": satisfaction_rate,
                "avg_resolution_per_group": avg_resolution_per_group,
                "sla_breach_rate": sla_breach_rate,
            },
            "prev_metrics": prev_metrics,
            "sla_daily": sla_daily,
            "satisfaction_daily": satisfaction_daily,
            "by_category": by_category_with_pct,
            "by_subcategory": by_subcategory,
        }
    }


@stats_router.get("/stats/trend")
async def trend_stats(
    date_from: str | None = None,
    date_to: str | None = None,
    skill_group_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    """按天返回新增/闭环趋势，供折线图使用。"""
    from datetime import date, datetime, timedelta, timezone

    today = date.today()
    if not date_from or not date_to:
        date_from = (today - timedelta(days=13)).isoformat()
        date_to = today.isoformat()

    start = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc, hour=23, minute=59, second=59)

    base = [Ticket.created_at >= start, Ticket.created_at <= end]
    if skill_group_id:
        base.append(Ticket.skill_group_id == skill_group_id)

    # 按天分组：新增量（created_at 落在哪天）
    new_rows = (await db.execute(
        select(func.date(Ticket.created_at).label("d"), func.count(Ticket.id))
        .where(*base)
        .group_by("d").order_by("d")
    )).all()
    # 按天分组：闭环量（closed_at 落在哪天）
    closed_rows = (await db.execute(
        select(func.date(Ticket.closed_at).label("d"), func.count(Ticket.id))
        .where(*base, Ticket.closed_at.is_not(None))
        .group_by("d").order_by("d")
    )).all()

    new_map = {str(r[0]): r[1] for r in new_rows}
    closed_map = {str(r[0]): r[1] for r in closed_rows}

    # 按天分组：当日超时工单数（sla_solution_breached == True 且 created_at 落在当天）
    overdue_rows = (await db.execute(
        select(func.date(Ticket.created_at).label("d"), func.count(Ticket.id))
        .where(*base, Ticket.sla_solution_breached == True)
        .group_by("d").order_by("d")
    )).all()
    overdue_map = {str(r[0]): r[1] for r in overdue_rows}

    # 补全每一天（即使没数据也填 0）；total = 累计未关闭工单数
    days = []
    cur = start.date()
    end_d = end.date()
    running_total = 0
    while cur <= end_d:
        key = cur.isoformat()
        d_new = new_map.get(key, 0)
        d_closed = closed_map.get(key, 0)
        running_total += d_new - d_closed
        days.append({
            "date": key,
            "new": d_new,
            "closed": d_closed,
            "overdue": overdue_map.get(key, 0),
            "total": max(running_total, 0),
        })
        cur += timedelta(days=1)

    return {"data": {"date_from": date_from, "date_to": date_to, "days": days}}
