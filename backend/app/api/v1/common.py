"""Users, Groups, SkillGroups, Categories, Regions, SLA, Stats routers."""

import math
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.exceptions import NotFoundError
from app.core.security import hash_password
from app.models.category import TicketCategory, Region
from app.models.dispatch import DispatchChain
from app.models.group import Group, SkillGroup, UserSkillGroup
from app.models.node_form import TicketNodeSubmission
from app.models.routing import CategoryRoutingRule
from app.models.sla import SLAPolicy
from app.models.ticket import Ticket, TicketStateLog
from app.models.user import User
from app.schemas.common import (
    CategoryCreate, CategoryOut, CategoryUpdate, DashboardStats, GroupCreate,
    GroupOut, RegionCreate, RegionOut, RoutingRuleCreate, RoutingRuleOut,
    RoutingRuleUpdate, SLAPolicyCreate, SLAPolicyOut,
    SkillGroupCreate, SkillGroupOut, UserCreate, UserOut, UserUpdate,
)
from app.services.category_utils import (
    build_category_path, build_lineage_index, compute_level, would_create_cycle,
    create_selectable_categories,
    INSTANT_CONSULT_CATEGORY_ID,
)  # noqa: F401  (build_category_path used elsewhere if needed)
from app.services.notification import send_dingtalk_text
from app.services.routing import create_rule, resolve_rule, update_rule

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
    if body.role == "agent" and body.group_id is None:
        raise HTTPException(422, detail="客服坐席必须选择客服组")
    if body.role == "handler" and not body.skill_groups:
        raise HTTPException(422, detail="处理人必须选择所属对接部门")

    u = User(
        username=body.username, name=body.name, phone=body.phone,
        password_hash=hash_password(body.password), role=body.role,
        local_login_enabled=True,
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

    next_role = body.role if body.role is not None else u.role
    if next_role == "agent" and (body.group_id if body.group_id is not None else u.group_id) is None:
        raise HTTPException(422, detail="客服坐席必须选择客服组")
    if next_role == "handler":
        has_membership = bool(body.skill_groups) if body.skill_groups is not None else bool((await db.execute(
            select(UserSkillGroup.user_id).where(UserSkillGroup.user_id == user_id).limit(1)
        )).scalar_one_or_none())
        if not has_membership:
            raise HTTPException(422, detail="处理人必须选择所属对接部门")

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
        if not u.casdoor_subject:
            u.local_login_enabled = True
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
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(User).join(UserSkillGroup, UserSkillGroup.user_id == User.id).where(
            UserSkillGroup.skill_group_id == group_id,
            UserSkillGroup.is_dispatcher == True,
            User.is_active == True,
            or_(UserSkillGroup.effective_from.is_(None), UserSkillGroup.effective_from <= now),
            or_(UserSkillGroup.effective_to.is_(None), UserSkillGroup.effective_to >= now),
        ).order_by(User.id)
    )
    users = result.scalars().all()
    return {"data": [{"id": u.id, "name": u.name, "username": u.username} for u in users]}


@skill_groups_router.get("/skill-groups/{group_id}/handlers")
async def list_handlers(group_id: int, db: AsyncSession = Depends(get_db), user: User = Depends(get_current_user)):
    """获取某对接部门的处理人列表（分派时选处理人用），部门对接人也可作为处理人。"""
    from app.models.group import UserSkillGroup
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(User).join(UserSkillGroup, UserSkillGroup.user_id == User.id).where(
            UserSkillGroup.skill_group_id == group_id,
            User.is_active == True,
            or_(UserSkillGroup.effective_from.is_(None), UserSkillGroup.effective_from <= now),
            or_(UserSkillGroup.effective_to.is_(None), UserSkillGroup.effective_to >= now),
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
    """Return the full category tree (arbitrary depth).

    Each node carries `level` (derived from parent chain) and `path` (display
    path e.g. "客户服务 / 业务保障 / 星座大系统"). `path` is best-effort
    computed when the response is assembled; depth is unlimited.
    """
    query = select(TicketCategory)
    show_all = include_inactive is True or str(include_inactive).lower() == "true"
    if not show_all:
        query = query.where(TicketCategory.is_active == True)
    result = await db.execute(query.order_by(TicketCategory.sort_order, TicketCategory.id))
    all_cats = list(result.scalars().all())
    if not all_cats:
        return {"data": []}

    # Compute derived attributes (level + path) up-front.
    by_id = {c.id: c for c in all_cats}
    levels: dict[int, int] = {}
    paths: dict[int, str] = {}

    def _level_of(c: TicketCategory, stack: set[int]) -> int:
        if c.id in levels:
            return levels[c.id]
        if c.parent_id is None or c.parent_id not in by_id:
            levels[c.id] = 1
            return 1
        if c.id in stack:
            # Defensive: should never happen post-cycle-detection.
            levels[c.id] = 1
            return 1
        stack.add(c.id)
        try:
            levels[c.id] = _level_of(by_id[c.parent_id], stack) + 1
        finally:
            stack.discard(c.id)
        return levels[c.id]

    for c in all_cats:
        _level_of(c, set())
        path_chain = []
        cur = c
        stack = set()
        while cur is not None:
            path_chain.append(cur.name)
            if cur.parent_id is None or cur.parent_id not in by_id:
                break
            if cur.parent_id in stack:
                break
            stack.add(cur.parent_id)
            cur = by_id[cur.parent_id]
        path_chain.reverse()
        paths[c.id] = " / ".join(path_chain)

    # 建单通道标注（V0.21 §4 表A，设计的表单放宽依据）：
    # - channel:     chain=按分派链自动落位；manual=无链人工分派
    # - create_selectable: 客服建单可选的"判断终点"——自身有通道（链/
    #   链末叶子），且祖先里没有判断链节点：业务保障/星座大系统这类判断节点
    #   的下级由处理侧分诊产生，不进客服建单表单。
    chain_cat_ids = set(
        (await db.execute(
            select(DispatchChain.category_id).where(DispatchChain.enabled == True)  # noqa: E712
        )).scalars()
    )

    def _has_chain(cid: int | None) -> bool:
        """沿父链上溯，任一祖先（含自身）配有启用链即算有链。"""
        seen: set[int] = set()
        while cid is not None and cid not in seen:
            seen.add(cid)
            if cid in chain_cat_ids:
                return True
            parent = by_id.get(cid)
            cid = parent.parent_id if parent else None
        return False

    active_children: dict[int, int] = {}
    for c in all_cats:
        if c.parent_id is not None:
            active_children[c.parent_id] = active_children.get(c.parent_id, 0) + 1

    channels: dict[int, str] = {}
    selectable = create_selectable_categories(all_cats, chain_cat_ids)
    for c in all_cats:
        has_chain = _has_chain(c.id)
        is_leaf = active_children.get(c.id, 0) == 0
        channels[c.id] = "instant" if c.id == INSTANT_CONSULT_CATEGORY_ID else ("chain" if has_chain else ("manual" if is_leaf else "none"))

    # Build tree.
    node_map: dict[int, dict] = {}
    for c in all_cats:
        node_map[c.id] = {
            "id": c.id,
            "name": c.name,
            "level": levels[c.id],
            "parent_id": c.parent_id,
            "sort_order": c.sort_order,
            "is_active": c.is_active,
            "path": paths[c.id],
            "channel": channels[c.id],
            "create_selectable": selectable.get(c.id, False),
            "children": [],
        }
    tree = []
    for c in all_cats:
        node = node_map[c.id]
        if c.parent_id and c.parent_id in node_map:
            node_map[c.parent_id]["children"].append(node)
        else:
            tree.append(node)
    return {"data": tree}


@categories_router.post("/categories", status_code=status.HTTP_201_CREATED)
async def create_category(
    body: CategoryCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """Create a category at any depth. parent_id optional (top-level when None)."""
    parent_cat = None
    if body.parent_id is not None:
        parent_cat = await db.execute(
            select(TicketCategory).where(TicketCategory.id == body.parent_id)
        )
        parent_cat = parent_cat.scalar_one_or_none()
        if not parent_cat:
            raise HTTPException(400, detail="父级分类不存在")

    # 同级名称去重（仅在 parent_id 范围内判重，与 level 解耦）
    dup_cond = [
        TicketCategory.name == body.name,
        TicketCategory.parent_id == body.parent_id,
    ]
    existing = await db.execute(select(TicketCategory).where(*dup_cond))
    if existing.scalar_one_or_none():
        raise HTTPException(400, detail="同级下已存在同名分类")

    cat = TicketCategory(
        name=body.name,
        parent_id=body.parent_id,
        level=1,  # 占位；list 接口会按 parent 链重算
        sort_order=body.sort_order,
        is_active=body.is_active,
    )
    db.add(cat)
    await db.flush()
    derived_level = await compute_level(db, cat)
    # 持久化派生 level 以便历史快照/兼容旧代码
    cat.level = derived_level
    await db.flush()
    return {
        "data": {
            "id": cat.id,
            "name": cat.name,
            "level": derived_level,
            "parent_id": cat.parent_id,
            "sort_order": cat.sort_order,
            "is_active": cat.is_active,
        }
    }


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

    # parent_id 变更：校验目标 parent 存在且不形成环
    if "parent_id" in body.model_fields_set and body.parent_id != cat.parent_id:
        if body.parent_id is not None:
            new_parent = await db.execute(
                select(TicketCategory).where(TicketCategory.id == body.parent_id)
            )
            if not new_parent.scalar_one_or_none():
                raise HTTPException(400, detail="父级分类不存在")
            if await would_create_cycle(db, node_id=category_id, new_parent_id=body.parent_id):
                raise HTTPException(400, detail="不能将分类移动到自身或其子孙下")
        cat.parent_id = body.parent_id

    # 改名时校验同级同名（parent 可能刚改过，按新 parent 判重）
    if body.name is not None and body.name != cat.name:
        dup_cond = [
            TicketCategory.name == body.name,
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

    # 重新派生 level（仅当 parent 链变动时才有意义，但开销低，统一重算）
    cat.level = await compute_level(db, cat)
    # parent 变了，子树的 level 也得跟着重算
    await _recompute_descendant_levels(db, cat.id)
    await db.flush()
    return {
        "data": {
            "id": cat.id,
            "name": cat.name,
            "level": cat.level,
            "parent_id": cat.parent_id,
            "sort_order": cat.sort_order,
            "is_active": cat.is_active,
        }
    }


async def _recompute_descendant_levels(db: AsyncSession, root_id: int) -> None:
    """Recompute `level` for every descendant of `root_id`.

    Depth-first traversal with a visited set to defend against cycles.
    """
    stack: list[int] = [root_id]
    visited: set[int] = set()
    while stack:
        current_id = stack.pop()
        if current_id in visited:
            continue
        visited.add(current_id)
        # compute_level walks up the chain; safe even if current row not yet flushed.
        current = await db.execute(
            select(TicketCategory).where(TicketCategory.id == current_id)
        )
        cat = current.scalar_one_or_none()
        if cat is None:
            continue
        new_level = await compute_level(db, cat)
        if cat.level != new_level:
            cat.level = new_level
        children = await db.execute(
            select(TicketCategory.id).where(TicketCategory.parent_id == current_id)
        )
        for (child_id,) in children.all():
            stack.append(child_id)


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

    # 任意深度：只要有子节点就拒绝
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

    # 6. 按完整分类路径归到一级、二级；工单可能挂在树中的任意层级。
    lineage = await build_lineage_index(db)
    roots = sorted(
        (item.l1 for cid, item in lineage.items()
         if item.l1 is not None and cid == item.l1.id and item.l1.is_active),
        key=lambda category: (category.sort_order, category.id),
    )
    root_counts = {root.id: 0 for root in roots}
    sub_counts: dict[int, dict[str, int]] = {root.id: {} for root in roots}
    category_trend: dict[str, dict[str, int]] = {}
    cat_daily_rows = (await db.execute(
        select(func.date(Ticket.created_at), Ticket.category_id, func.count(Ticket.id))
        .where(*base, Ticket.category_id.is_not(None))
        .group_by(func.date(Ticket.created_at), Ticket.category_id)
    )).all()
    for day, category_id, count in cat_daily_rows:
        item = lineage.get(category_id)
        if item is None or item.l1 is None or item.l1.id not in root_counts:
            continue
        root = item.l1
        root_counts[root.id] += count
        sub_name = item.l2.name if item.l2 is not None else "待确定二级分类"
        sub_counts[root.id][sub_name] = sub_counts[root.id].get(sub_name, 0) + count
        trend = category_trend.setdefault(root.name, {})
        day_key = str(day)
        trend[day_key] = trend.get(day_key, 0) + count
    by_category = [{"name": root.name, "count": root_counts[root.id]} for root in roots]
    by_subcategory = {
        root.name: [
            {"name": name, "count": count}
            for name, count in sorted(sub_counts[root.id].items(), key=lambda entry: -entry[1])
        ]
        for root in roots
    }

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


@stats_router.get("/stats/service-analysis")
async def service_analysis_stats(
    date_from: str | None = None,
    date_to: str | None = None,
    skill_group_id: int | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    """全量工单总览。时间范围按北京时间的建单日期筛选。"""
    from collections import Counter, defaultdict
    from datetime import date, time

    local_tz = timezone(timedelta(hours=8))
    today = datetime.now(local_tz).date()
    try:
        first = date.fromisoformat(date_from) if date_from else today.replace(day=1)
        last = date.fromisoformat(date_to) if date_to else today
    except ValueError as exc:
        raise HTTPException(422, detail="日期格式应为 YYYY-MM-DD") from exc
    if first > last or (last - first).days > 366:
        raise HTTPException(422, detail="日期范围无效或超过 366 天")

    start = datetime.combine(first, time.min, local_tz).astimezone(timezone.utc)
    end = datetime.combine(last + timedelta(days=1), time.min, local_tz).astimezone(timezone.utc)
    span = (last - first).days + 1
    prev_start, prev_end = start - timedelta(days=span), start
    filters = [Ticket.is_draft.is_(False)]
    if skill_group_id is not None:
        filters.append(Ticket.skill_group_id == skill_group_id)

    async def load_tickets(begin: datetime, finish: datetime):
        return (await db.execute(select(Ticket).where(
            *filters, Ticket.created_at >= begin, Ticket.created_at < finish,
        ).options(selectinload(Ticket.owner)))).scalars().all()

    current = await load_tickets(start, end)
    previous = await load_tickets(prev_start, prev_end)
    now = datetime.now(timezone.utc)
    closed_states = {"archived", "cancelled"}

    def is_closed(ticket: Ticket) -> bool:
        return ticket.closed_at is not None or ticket.state in closed_states

    def is_overdue(ticket: Ticket) -> bool:
        return bool(ticket.sla_solution_breached or (
            not is_closed(ticket) and ticket.solution_deadline is not None
            and ticket.solution_deadline < now
        ))

    def satisfaction(ticket: Ticket) -> bool | None:
        if ticket.customer_recognized is not None:
            return ticket.customer_recognized
        if ticket.satisfaction in {"satisfied", "average", "dissatisfied"}:
            return ticket.satisfaction == "satisfied"
        return None

    def metrics(tickets: list[Ticket]) -> dict:
        rated = [satisfaction(ticket) for ticket in tickets]
        rated = [value for value in rated if value is not None]
        count = len(tickets)
        return {
            "total": count,
            "service_count": sum(ticket.is_opportunity is not True for ticket in tickets),
            "opportunity_count": sum(ticket.is_opportunity is True for ticket in tickets),
            "closed_count": sum(is_closed(ticket) for ticket in tickets),
            "closure_rate": round(sum(is_closed(ticket) for ticket in tickets) / count, 4) if count else 0,
            "overdue_count": sum(is_overdue(ticket) for ticket in tickets),
            "overdue_rate": round(sum(is_overdue(ticket) for ticket in tickets) / count, 4) if count else 0,
            "satisfied_count": sum(value is True for value in rated),
            "rated_count": len(rated),
            "satisfaction_rate": round(sum(value is True for value in rated) / len(rated), 4) if rated else None,
            "long_open_count": sum(not is_closed(ticket) and now - ticket.created_at >= timedelta(hours=72) for ticket in tickets),
            "dissatisfied_count": sum(satisfaction(ticket) is False for ticket in tickets),
        }

    lineage = await build_lineage_index(db)
    categories: Counter[str] = Counter()
    subcategories: Counter[tuple[str, str]] = Counter()
    for ticket in current:
        item = lineage.get(ticket.category_id)
        root = "线索工单" if ticket.is_opportunity else (item.l1.name if item and item.l1 else "未分类")
        sub = "销售线索" if ticket.is_opportunity else (item.l2.name if item and item.l2 else "未细分")
        categories[root] += 1
        subcategories[(root, sub)] += 1

    daily: dict[str, dict[str, int]] = defaultdict(lambda: {"new": 0, "closed": 0})
    for ticket in current:
        created_day = ticket.created_at.astimezone(local_tz).date().isoformat()
        daily[created_day]["new"] += 1
        if ticket.closed_at is not None and start <= ticket.closed_at < end:
            closed_day = ticket.closed_at.astimezone(local_tz).date().isoformat()
            daily[closed_day]["closed"] += 1
    days = []
    cursor = first
    while cursor <= last:
        key = cursor.isoformat()
        days.append({"date": key, **daily[key]})
        cursor += timedelta(days=1)

    abnormal = sorted(
        (ticket for ticket in current if is_overdue(ticket) or
         (not is_closed(ticket) and now - ticket.created_at >= timedelta(hours=72)) or
         satisfaction(ticket) is False),
        key=lambda ticket: ticket.created_at, reverse=True,
    )[:8]
    return {"data": {
        "date_from": first.isoformat(), "date_to": last.isoformat(),
        "metrics": metrics(current), "prev_metrics": metrics(previous),
        "trend": days,
        "by_category": [{"name": name, "count": count} for name, count in categories.most_common()],
        "by_subcategory": [{"root": root, "name": name, "count": count}
                           for (root, name), count in subcategories.most_common()],
        "abnormal_tickets": [{
            "id": ticket.id, "number": ticket.number, "category": (
                "线索工单" if ticket.is_opportunity else lineage[ticket.category_id].l1.name if ticket.category_id in lineage
                and lineage[ticket.category_id].l1 else "未分类"),
            "subcategory": ("销售线索" if ticket.is_opportunity else lineage[ticket.category_id].l2.name if ticket.category_id in lineage
                             and lineage[ticket.category_id].l2 else "未细分"),
            "owner": ticket.owner.name if ticket.owner else "未指派",
            "state": ticket.state,
            "reason": "SLA 超时" if is_overdue(ticket) else (
                "客户不满意" if satisfaction(ticket) is False else "超过 72 小时未办结"),
            "age_hours": round((now - ticket.created_at).total_seconds() / 3600, 1),
        } for ticket in abnormal],
    }}


# ── 线索工单分析 ────────────────────────────────────────────

# 建单界面「受理渠道」展示名 ⇄ tickets.channel 存储值（与前端 channelCodes 对齐）
OPPORTUNITY_CHANNEL_LABELS = {"phone": "语音", "web": "在线客服", "internal": "内部转办"}

# 销售处理时长分桶（小时）
OPPORTUNITY_DURATION_BUCKETS = (
    ("<2小时", 0, 2),
    ("2-4小时", 2, 4),
    ("4-8小时", 4, 8),
    ("8-24小时", 8, 24),
    (">24小时", 24, None),
)


def _opportunity_percentile(sorted_values: list[float], p: float) -> float | None:
    """线性插值分位数；sorted_values 必须已升序排序。"""
    if not sorted_values:
        return None
    k = (len(sorted_values) - 1) * p
    lower = math.floor(k)
    upper = math.ceil(k)
    if lower == upper:
        return sorted_values[int(k)]
    return sorted_values[lower] * (upper - k) + sorted_values[upper] * (k - lower)


def _opportunity_bucket_key(day, granularity: str):
    """趋势分桶键：按天返回当天；按周返回本周一。"""
    if granularity == "week":
        return day - timedelta(days=day.weekday())
    return day


async def _opportunity_snapshot(
    db: AsyncSession, start: datetime, end: datetime,
    channel: str | None, industry: str | None, owner_id: int | None,
) -> dict:
    """统计 [start, end] 内创建的线索工单（is_opportunity 且非草稿）。

    数据来源全部为真实字段：
    - 线索工单总量 / 渠道 / 行业 / 销售承接：tickets 表
    - 已完成销售判断 / 有效线索 / 客户评级 / 销售处理时长：
      ticket_node_submissions 表中 node_type='sales_opportunity' 的提交记录
    """
    base = [
        Ticket.is_opportunity == True,  # noqa: E712
        Ticket.is_draft == False,  # noqa: E712
        Ticket.created_at >= start,
        Ticket.created_at <= end,
    ]
    if channel:
        base.append(Ticket.channel == channel)
    if industry:
        base.append(Ticket.industry == industry)
    if owner_id:
        base.append(Ticket.owner_id == owner_id)

    ticket_rows = (await db.execute(
        select(
            Ticket.id, Ticket.number, Ticket.customer_name, Ticket.customer_company,
            Ticket.industry, Ticket.channel, Ticket.state, Ticket.owner_id,
            Ticket.created_at,
        ).where(*base)
    )).all()

    submission_by_ticket: dict[int, object] = {}
    if ticket_rows:
        ticket_ids = [row[0] for row in ticket_rows]
        submission_rows = (await db.execute(
            select(
                TicketNodeSubmission.ticket_id, TicketNodeSubmission.data,
                TicketNodeSubmission.submitted_at, TicketNodeSubmission.operator_id,
            ).where(
                TicketNodeSubmission.ticket_id.in_(ticket_ids),
                TicketNodeSubmission.node_type == "sales_opportunity",
            ).order_by(TicketNodeSubmission.submitted_at, TicketNodeSubmission.id)
        )).all()
        for ticket_id, data, submitted_at, _operator_id in submission_rows:
            submission_by_ticket[ticket_id] = (data or {}, submitted_at)

    # ── KPI ──
    total = len(ticket_rows)
    judged = 0
    valid = 0
    ratings: list[float] = []
    valid_ratings: list[float] = []
    invalid_ratings: list[float] = []
    durations: list[float] = []
    created_by_day: dict[str, int] = {}
    judged_by_day: dict[str, int] = {}
    valid_by_day: dict[str, int] = {}
    channel_stat: dict[str, dict] = {}
    industry_stat: dict[str, dict] = {}
    owner_stat: dict[int, dict] = {}
    owner_durations: dict[int, list[float]] = {}
    rating_dist = {str(star): 0 for star in range(1, 6)}
    bucket_counts = {label: 0 for label, _lo, _hi in OPPORTUNITY_DURATION_BUCKETS}

    def _stat_entry() -> dict:
        return {"total": 0, "judged": 0, "valid": 0}

    for row in ticket_rows:
        (ticket_id, _number, _customer_name, _company, row_industry,
         row_channel, _state, row_owner, created_at) = row
        day_key = _opportunity_bucket_key(created_at.date(), "day").isoformat()
        created_by_day[day_key] = created_by_day.get(day_key, 0) + 1
        for stat_map, key in ((channel_stat, row_channel), (industry_stat, row_industry)):
            entry = stat_map.setdefault(key, _stat_entry())
            entry["total"] += 1
        if row_owner is not None:
            owner_stat.setdefault(row_owner, _stat_entry())["total"] += 1

        submission = submission_by_ticket.get(ticket_id)
        if submission is None:
            continue
        data, submitted_at = submission
        judged += 1
        channel_stat[row_channel]["judged"] += 1
        industry_stat[row_industry]["judged"] += 1
        if row_owner is not None:
            owner_stat[row_owner]["judged"] += 1
        submit_day = _opportunity_bucket_key(submitted_at.date(), "day").isoformat()
        judged_by_day[submit_day] = judged_by_day.get(submit_day, 0) + 1

        rating_raw = data.get("customer_rating")
        if rating_raw is not None:
            try:
                star = int(rating_raw)
            except (TypeError, ValueError):
                star = None
            if star is not None and 1 <= star <= 5:
                ratings.append(float(star))
                rating_dist[str(star)] += 1
                if data.get("valid_opportunity") is True:
                    valid_ratings.append(float(star))
                else:
                    invalid_ratings.append(float(star))

        if data.get("valid_opportunity") is True:
            valid += 1
            channel_stat[row_channel]["valid"] += 1
            industry_stat[row_industry]["valid"] += 1
            if row_owner is not None:
                owner_stat[row_owner]["valid"] += 1
            valid_by_day[submit_day] = valid_by_day.get(submit_day, 0) + 1

        # 销售处理时长 = 销售线索表单提交时间 - 工单创建时间
        if submitted_at is not None and created_at is not None:
            hours = (submitted_at - created_at).total_seconds() / 3600
            if hours >= 0:
                durations.append(hours)
                if row_owner is not None:
                    owner_durations.setdefault(row_owner, []).append(hours)
                for label, lo, hi in OPPORTUNITY_DURATION_BUCKETS:
                    if hours >= lo and (hi is None or hours < hi):
                        bucket_counts[label] += 1
                        break

    durations.sort()
    kpi = {
        "total": total,
        "judged": judged,
        "valid": valid,
        "valid_rate": round(valid / judged, 4) if judged else 0.0,
        "avg_rating": round(sum(ratings) / len(ratings), 2) if ratings else None,
        "avg_handle_hours": round(sum(durations) / len(durations), 2) if durations else None,
    }

    def _rate(entry: dict) -> float:
        return round(entry["valid"] / entry["judged"], 4) if entry["judged"] else 0.0

    def _owner_entry(owner_id: int, entry: dict) -> dict:
        hours = owner_durations.get(owner_id, [])
        return {
            "total": entry["total"], "judged": entry["judged"],
            "valid": entry["valid"], "valid_rate": _rate(entry),
            "avg_hours": round(sum(hours) / len(hours), 2) if hours else None,
        }

    return {
        "kpi": kpi,
        "created_by_day": created_by_day,
        "judged_by_day": judged_by_day,
        "valid_by_day": valid_by_day,
        "by_channel": [
            {"channel": key, "total": entry["total"], "judged": entry["judged"],
             "valid": entry["valid"], "valid_rate": _rate(entry)}
            for key, entry in sorted(channel_stat.items(), key=lambda kv: -kv[1]["total"])
        ],
        "by_industry": [
            {"industry": key or "未提供", "total": entry["total"], "judged": entry["judged"],
             "valid": entry["valid"], "valid_rate": _rate(entry)}
            for key, entry in sorted(industry_stat.items(), key=lambda kv: -kv[1]["total"])
        ],
        "by_owner": {
            owner_id: _owner_entry(owner_id, entry)
            for owner_id, entry in owner_stat.items()
        },
        "rating_distribution": rating_dist,
        "valid_avg_rating": round(sum(valid_ratings) / len(valid_ratings), 2) if valid_ratings else None,
        "invalid_avg_rating": round(sum(invalid_ratings) / len(invalid_ratings), 2) if invalid_ratings else None,
        "duration": {
            "avg_hours": round(sum(durations) / len(durations), 2) if durations else None,
            "p50_hours": (lambda v: round(v, 2) if v is not None else None)(_opportunity_percentile(durations, 0.5)),
            "p90_hours": (lambda v: round(v, 2) if v is not None else None)(_opportunity_percentile(durations, 0.9)),
            "buckets": [
                {"label": label, "count": bucket_counts[label]}
                for label, _lo, _hi in OPPORTUNITY_DURATION_BUCKETS
            ],
        },
    }


@stats_router.get("/stats/opportunity-analysis")
async def opportunity_analysis_stats(
    date_from: str | None = None,
    date_to: str | None = None,
    channel: str | None = None,
    industry: str | None = None,
    owner_id: int | None = None,
    granularity: str = Query("day", pattern="^(day|week)$"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin", "agent")),
):
    """线索工单分析：机会识别、有效性判断与销售承接效率。

    仅统计 is_opportunity=True 且非草稿工单；销售判断结果取自
    sales_opportunity 节点提交（有效线索 / 客户评级 / 处理时长）。
    """
    from datetime import date

    today = date.today()
    if not date_from or not date_to:
        date_to = today.isoformat()
        date_from = (today - timedelta(days=29)).isoformat()

    start = datetime.fromisoformat(date_from).replace(tzinfo=timezone.utc)
    end = datetime.fromisoformat(date_to).replace(tzinfo=timezone.utc, hour=23, minute=59, second=59)

    snapshot = await _opportunity_snapshot(db, start, end, channel, industry, owner_id)

    # 上一周期（用于 KPI「较上一周期」对比）
    span_days = (end.date() - start.date()).days + 1
    prev_end_date = start.date() - timedelta(days=1)
    prev_start_date = prev_end_date - timedelta(days=span_days - 1)
    prev_start = datetime.combine(prev_start_date, datetime.min.time()).replace(tzinfo=timezone.utc)
    prev_end = datetime.combine(prev_end_date, datetime.max.time()).replace(tzinfo=timezone.utc)
    prev_snapshot = await _opportunity_snapshot(db, prev_start, prev_end, channel, industry, owner_id)

    # ── 趋势（按天/周分桶，补全无数据桶）──
    if granularity == "week":
        def _to_weekly(daily: dict[str, int]) -> dict[str, int]:
            weekly: dict[str, int] = {}
            for day_key, count in daily.items():
                week_key = _opportunity_bucket_key(
                    date.fromisoformat(day_key), "week",
                ).isoformat()
                weekly[week_key] = weekly.get(week_key, 0) + count
            return weekly

        trend_created = _to_weekly(snapshot["created_by_day"])
        trend_judged = _to_weekly(snapshot["judged_by_day"])
        trend_valid = _to_weekly(snapshot["valid_by_day"])
    else:
        trend_created = snapshot["created_by_day"]
        trend_judged = snapshot["judged_by_day"]
        trend_valid = snapshot["valid_by_day"]

    trend: list[dict] = []
    cur = _opportunity_bucket_key(start.date(), granularity)
    last = _opportunity_bucket_key(end.date(), granularity)
    step = timedelta(days=7 if granularity == "week" else 1)
    while cur <= last:
        key = cur.isoformat()
        trend.append({
            "date": key,
            "created": trend_created.get(key, 0),
            "judged": trend_judged.get(key, 0),
            "valid": trend_valid.get(key, 0),
        })
        cur += step

    # ── 销售承接分析（负责人维度）──
    owner_ids = [oid for oid in snapshot["by_owner"] if oid is not None]
    owner_names: dict[int, str] = {}
    if owner_ids:
        owner_rows = (await db.execute(
            select(User.id, User.name).where(User.id.in_(owner_ids))
        )).all()
        owner_names = {row[0]: row[1] for row in owner_rows}
    by_salesperson = []
    for oid, entry in sorted(snapshot["by_owner"].items(), key=lambda kv: -kv[1]["total"]):
        if oid is None:
            continue
        by_salesperson.append({
            "owner_id": oid,
            "name": owner_names.get(oid, f"用户{oid}"),
            "assigned": entry["total"],
            "judged": entry["judged"],
            "valid": entry["valid"],
            "valid_rate": entry["valid_rate"],
            "avg_hours": entry["avg_hours"],
        })

    # ── 近期线索工单（最近 8 条）──
    recent_rows = (await db.execute(
        select(
            Ticket.id, Ticket.number, Ticket.customer_name, Ticket.industry,
            Ticket.state, Ticket.owner_id, Ticket.created_at,
        )
        .where(
            Ticket.is_opportunity == True,  # noqa: E712
            Ticket.is_draft == False,  # noqa: E712
            Ticket.created_at >= start,
            Ticket.created_at <= end,
            *([Ticket.channel == channel] if channel else []),
            *([Ticket.industry == industry] if industry else []),
            *([Ticket.owner_id == owner_id] if owner_id else []),
        )
        .order_by(Ticket.created_at.desc(), Ticket.id.desc())
        .limit(8)
    )).all()
    recent_ticket_ids = [row[0] for row in recent_rows]
    recent_submission: dict[int, tuple] = {}
    if recent_ticket_ids:
        sub_rows = (await db.execute(
            select(
                TicketNodeSubmission.ticket_id, TicketNodeSubmission.data,
            ).where(
                TicketNodeSubmission.ticket_id.in_(recent_ticket_ids),
                TicketNodeSubmission.node_type == "sales_opportunity",
            ).order_by(TicketNodeSubmission.submitted_at, TicketNodeSubmission.id)
        )).all()
        for ticket_id, data in sub_rows:
            recent_submission[ticket_id] = (data or {})
    recent_tickets = []
    for row in recent_rows:
        ticket_id, number, customer_name, row_industry, state, _owner, _created = row
        data = recent_submission.get(ticket_id, {})
        recent_tickets.append({
            "id": ticket_id,
            "number": number,
            "customer_name": customer_name,
            "industry": row_industry or "未提供",
            "state": state,
            "valid_opportunity": data.get("valid_opportunity"),
            "customer_rating": data.get("customer_rating"),
        })

    # ── 筛选项（不受日期/筛选影响，覆盖全部线索工单）──
    option_rows = (await db.execute(
        select(Ticket.channel, Ticket.industry, Ticket.owner_id)
        .where(
            Ticket.is_opportunity == True,  # noqa: E712
            Ticket.is_draft == False,  # noqa: E712
        )
    )).all()
    channel_values = sorted({row[0] for row in option_rows if row[0]})
    industry_values = sorted({row[1] for row in option_rows if row[1]})
    owner_values = sorted({row[2] for row in option_rows if row[2] is not None})
    owner_option_names: dict[int, str] = {}
    if owner_values:
        name_rows = (await db.execute(
            select(User.id, User.name).where(User.id.in_(owner_values))
        )).all()
        owner_option_names = {row[0]: row[1] for row in name_rows}

    return {"data": {
        "date_from": date_from,
        "date_to": date_to,
        "prev_date_from": prev_start_date.isoformat(),
        "prev_date_to": prev_end_date.isoformat(),
        "kpi": snapshot["kpi"],
        "prev_kpi": prev_snapshot["kpi"],
        "trend": trend,
        "by_channel": [
            {"channel": item["channel"],
             "label": OPPORTUNITY_CHANNEL_LABELS.get(item["channel"], item["channel"]),
             **item}
            for item in snapshot["by_channel"]
        ],
        "by_industry": snapshot["by_industry"],
        "rating_distribution": snapshot["rating_distribution"],
        "valid_avg_rating": snapshot["valid_avg_rating"],
        "invalid_avg_rating": snapshot["invalid_avg_rating"],
        "duration": snapshot["duration"],
        "by_salesperson": by_salesperson,
        "recent_tickets": recent_tickets,
        "options": {
            "channels": [
                {"value": value, "label": OPPORTUNITY_CHANNEL_LABELS.get(value, value)}
                for value in channel_values
            ],
            "industries": [{"value": value, "label": value} for value in industry_values],
            "salespersons": [
                {"value": oid, "label": owner_option_names.get(oid, f"用户{oid}")}
                for oid in owner_values
            ],
        },
    }}


# ── Category Routing Rules ──────────────────────────────────

routing_router = APIRouter(tags=["routing"])


def _serialize_rule(rule: CategoryRoutingRule, db: AsyncSession | None = None) -> dict:
    """Build a flat dict including denormalised names for the admin UI."""
    path = None
    if rule.category is not None and db is not None:
        # Build path from already-loaded relationship chain (lazy='selectin' fetches parent).
        chain = [rule.category]
        cur = rule.category
        visited = set()
        while cur is not None and cur.id not in visited:
            visited.add(cur.id)
            p = getattr(cur, "parent", None)
            if p is None or p.id == cur.id:
                break
            chain.append(p)
            cur = p
        chain.reverse()
        path = " / ".join(c.name for c in chain)
    return {
        "id": rule.id,
        "category_id": rule.category_id,
        "category_name": rule.category.name if rule.category else None,
        "category_path": path,
        "dispatcher_skill_group_id": rule.dispatcher_skill_group_id,
        "dispatcher_skill_group_name": rule.dispatcher_skill_group.name if rule.dispatcher_skill_group else None,
        "dispatcher_id": rule.dispatcher_id,
        "dispatcher_name": rule.dispatcher.name if rule.dispatcher else None,
        "handler_skill_group_id": rule.handler_skill_group_id,
        "handler_skill_group_name": rule.handler_skill_group.name if rule.handler_skill_group else None,
        "owner_id": rule.owner_id,
        "owner_name": rule.owner.name if rule.owner else None,
        "enabled": rule.enabled,
        "note": rule.note,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }


@routing_router.get("/routing-rules")
async def list_routing_rules(
    category_id: int | None = None,
    enabled: bool | None = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    q = select(CategoryRoutingRule).options(
        selectinload(CategoryRoutingRule.category).selectinload(TicketCategory.parent),
        selectinload(CategoryRoutingRule.dispatcher_skill_group),
        selectinload(CategoryRoutingRule.handler_skill_group),
        selectinload(CategoryRoutingRule.dispatcher),
        selectinload(CategoryRoutingRule.owner),
    )
    if category_id is not None:
        q = q.where(CategoryRoutingRule.category_id == category_id)
    if enabled is not None:
        q = q.where(CategoryRoutingRule.enabled == enabled)
    q = q.order_by(CategoryRoutingRule.id)
    rules = (await db.execute(q)).scalars().all()
    return {"data": [_serialize_rule(r) for r in rules]}


@routing_router.get("/routing-rules/{rule_id}")
async def get_routing_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    rule = (await db.execute(
        select(CategoryRoutingRule)
        .where(CategoryRoutingRule.id == rule_id)
        .options(
            selectinload(CategoryRoutingRule.category).selectinload(TicketCategory.parent),
            selectinload(CategoryRoutingRule.dispatcher_skill_group),
            selectinload(CategoryRoutingRule.handler_skill_group),
            selectinload(CategoryRoutingRule.dispatcher),
            selectinload(CategoryRoutingRule.owner),
        )
    )).scalar_one_or_none()
    if not rule:
        raise NotFoundError("路由规则", rule_id)
    return {"data": _serialize_rule(rule)}


@routing_router.post("/routing-rules", status_code=status.HTTP_201_CREATED)
async def create_routing_rule(
    body: RoutingRuleCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    rule = await create_rule(db, body)
    # Re-fetch with relationships loaded for response.
    rule = (await db.execute(
        select(CategoryRoutingRule)
        .where(CategoryRoutingRule.id == rule.id)
        .options(
            selectinload(CategoryRoutingRule.category).selectinload(TicketCategory.parent),
            selectinload(CategoryRoutingRule.dispatcher_skill_group),
            selectinload(CategoryRoutingRule.handler_skill_group),
            selectinload(CategoryRoutingRule.dispatcher),
            selectinload(CategoryRoutingRule.owner),
        )
    )).scalar_one()
    return {"data": _serialize_rule(rule)}


@routing_router.patch("/routing-rules/{rule_id}")
async def update_routing_rule(
    rule_id: int,
    body: RoutingRuleUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    rule = (await db.execute(
        select(CategoryRoutingRule).where(CategoryRoutingRule.id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise NotFoundError("路由规则", rule_id)
    await update_rule(db, rule, body)
    rule = (await db.execute(
        select(CategoryRoutingRule)
        .where(CategoryRoutingRule.id == rule_id)
        .options(
            selectinload(CategoryRoutingRule.category).selectinload(TicketCategory.parent),
            selectinload(CategoryRoutingRule.dispatcher_skill_group),
            selectinload(CategoryRoutingRule.handler_skill_group),
            selectinload(CategoryRoutingRule.dispatcher),
            selectinload(CategoryRoutingRule.owner),
        )
    )).scalar_one()
    return {"data": _serialize_rule(rule)}


@routing_router.delete("/routing-rules/{rule_id}")
async def delete_routing_rule(
    rule_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    rule = (await db.execute(
        select(CategoryRoutingRule).where(CategoryRoutingRule.id == rule_id)
    )).scalar_one_or_none()
    if not rule:
        raise NotFoundError("路由规则", rule_id)
    await db.delete(rule)
    await db.flush()
    return {"data": {"id": rule_id, "deleted": True}}


@routing_router.post("/routing-rules/resolve")
async def resolve_routing_rule(
    body: dict,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Return the suggested responsibility for a given category id.

    Used by the create-ticket form to autofill after the user picks a final
    category. The agent can still override manually.

    分派链（dispatch_chains）优先；无链回退旧 category_routing_rules。
    链命中时额外返回 chain_steps（前端可展示"将按链流转：A → B"）。
    """
    category_id = body.get("category_id") if isinstance(body, dict) else None
    from app.services.dispatch_chain import resolve_responsibility
    return {"data": await resolve_responsibility(db, category_id)}
