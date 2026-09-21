"""Routing-rule business logic: validation + resolve-from-category.

Validation rules for create/update:
- category_id must exist and be active
- dispatcher_skill_group_id, dispatcher_id must exist
- dispatcher_id must be a dispatcher of dispatcher_skill_group_id
  (i.e. a row in user_skill_groups with is_dispatcher=true)
- handler_skill_group_id (if provided) must exist
- owner_id (if provided) must exist
- if owner_id is given, owner must belong to handler_skill_group_id
- deactivating a user (is_active=false) does not invalidate historical
  routing rules but is reported in resolve()
"""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.category import TicketCategory
from app.models.group import SkillGroup, UserSkillGroup
from app.models.routing import CategoryRoutingRule
from app.models.user import User
from app.schemas.common import RoutingRuleCreate, RoutingRuleUpdate


async def _validate_dispatcher(
    db: AsyncSession, dispatcher_id: int, dispatcher_skill_group_id: int
) -> None:
    """dispatcher 必须属于 dispatcher_skill_group 且 is_dispatcher=true。"""
    link = await db.execute(
        select(UserSkillGroup).where(
            UserSkillGroup.user_id == dispatcher_id,
            UserSkillGroup.skill_group_id == dispatcher_skill_group_id,
        )
    )
    row = link.scalar_one_or_none()
    if not row or not row.is_dispatcher:
        raise HTTPException(
            400,
            detail="dispatcher_id 必须属于 dispatcher_skill_group，且标记为对接人",
        )


async def _validate_owner(
    db: AsyncSession, owner_id: int | None, handler_skill_group_id: int | None
) -> None:
    """owner_id 如果给了，必须属于 handler_skill_group。"""
    if owner_id is None:
        return
    if handler_skill_group_id is None:
        raise HTTPException(
            400, detail="owner_id 已填写时必须同时指定 handler_skill_group_id"
        )
    link = await db.execute(
        select(UserSkillGroup).where(
            UserSkillGroup.user_id == owner_id,
            UserSkillGroup.skill_group_id == handler_skill_group_id,
        )
    )
    if not link.scalar_one_or_none():
        raise HTTPException(
            400,
            detail="owner_id 必须属于 handler_skill_group_id",
        )


async def validate_rule_payload(
    db: AsyncSession,
    *,
    category_id: int,
    dispatcher_skill_group_id: int,
    dispatcher_id: int,
    handler_skill_group_id: int | None,
    owner_id: int | None,
) -> None:
    cat = await db.execute(
        select(TicketCategory).where(TicketCategory.id == category_id)
    )
    if not cat.scalar_one_or_none():
        raise HTTPException(400, detail="category_id 不存在")
    sg = await db.execute(
        select(SkillGroup).where(SkillGroup.id == dispatcher_skill_group_id)
    )
    if not sg.scalar_one_or_none():
        raise HTTPException(400, detail="dispatcher_skill_group_id 不存在")
    u = await db.execute(select(User).where(User.id == dispatcher_id))
    if not u.scalar_one_or_none():
        raise HTTPException(400, detail="dispatcher_id 不存在")
    if handler_skill_group_id is not None:
        sg2 = await db.execute(
            select(SkillGroup).where(SkillGroup.id == handler_skill_group_id)
        )
        if not sg2.scalar_one_or_none():
            raise HTTPException(400, detail="handler_skill_group_id 不存在")
    if owner_id is not None:
        u2 = await db.execute(select(User).where(User.id == owner_id))
        if not u2.scalar_one_or_none():
            raise HTTPException(400, detail="owner_id 不存在")

    await _validate_dispatcher(db, dispatcher_id, dispatcher_skill_group_id)
    await _validate_owner(db, owner_id, handler_skill_group_id)


async def create_rule(db: AsyncSession, body: RoutingRuleCreate) -> CategoryRoutingRule:
    await validate_rule_payload(
        db,
        category_id=body.category_id,
        dispatcher_skill_group_id=body.dispatcher_skill_group_id,
        dispatcher_id=body.dispatcher_id,
        handler_skill_group_id=body.handler_skill_group_id,
        owner_id=body.owner_id,
    )
    existing = await db.execute(
        select(CategoryRoutingRule).where(
            CategoryRoutingRule.category_id == body.category_id
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(409, detail="该分类已存在责任路由规则，请直接编辑")

    rule = CategoryRoutingRule(
        category_id=body.category_id,
        dispatcher_skill_group_id=body.dispatcher_skill_group_id,
        dispatcher_id=body.dispatcher_id,
        handler_skill_group_id=body.handler_skill_group_id,
        owner_id=body.owner_id,
        enabled=body.enabled,
        note=body.note,
    )
    db.add(rule)
    await db.flush()
    return rule


async def update_rule(
    db: AsyncSession, rule: CategoryRoutingRule, body: RoutingRuleUpdate
) -> CategoryRoutingRule:
    new_d_sg = (
        body.dispatcher_skill_group_id
        if body.dispatcher_skill_group_id is not None
        else rule.dispatcher_skill_group_id
    )
    new_d_id = body.dispatcher_id if body.dispatcher_id is not None else rule.dispatcher_id
    new_h_sg = (
        body.handler_skill_group_id
        if "handler_skill_group_id" in body.model_fields_set
        else rule.handler_skill_group_id
    )
    new_o_id = (
        body.owner_id
        if "owner_id" in body.model_fields_set
        else rule.owner_id
    )

    await validate_rule_payload(
        db,
        category_id=rule.category_id,
        dispatcher_skill_group_id=new_d_sg,
        dispatcher_id=new_d_id,
        handler_skill_group_id=new_h_sg,
        owner_id=new_o_id,
    )

    if body.dispatcher_skill_group_id is not None:
        rule.dispatcher_skill_group_id = body.dispatcher_skill_group_id
    if body.dispatcher_id is not None:
        rule.dispatcher_id = body.dispatcher_id
    if "handler_skill_group_id" in body.model_fields_set:
        rule.handler_skill_group_id = body.handler_skill_group_id
    if "owner_id" in body.model_fields_set:
        rule.owner_id = body.owner_id
    if body.enabled is not None:
        rule.enabled = body.enabled
    if body.note is not None:
        rule.note = body.note
    await db.flush()
    return rule


async def resolve_rule(
    db: AsyncSession, category_id: int | None
) -> dict:
    """Return the suggested responsibility set for a given category.

    Resolution order:
    1. Exact match on the leaf category
    2. Walk up the parent chain until a rule is found or root reached
       (so a level-2 routing rule applies to all its descendants)

    If no rule exists, return matched=False with reason. The create-ticket
    form falls back to manual mode in that case.
    """
    if category_id is None:
        return {
            "category_id": None,
            "matched": False,
            "reason": "未选择分类",
        }
    # Walk up the tree looking for a routing rule.
    cat_id = category_id
    visited: set[int] = set()
    rule = None
    matched_category_id = None
    while cat_id is not None and cat_id not in visited:
        visited.add(cat_id)
        r = await db.execute(
            select(CategoryRoutingRule)
            .where(CategoryRoutingRule.category_id == cat_id)
            .options(
                selectinload(CategoryRoutingRule.dispatcher),
                selectinload(CategoryRoutingRule.owner),
                selectinload(CategoryRoutingRule.dispatcher_skill_group),
                selectinload(CategoryRoutingRule.handler_skill_group),
                selectinload(CategoryRoutingRule.category),
            )
        )
        r = r.scalar_one_or_none()
        if r is not None:
            rule = r
            matched_category_id = cat_id
            break
        # Walk up to parent
        parent_row = await db.execute(
            select(TicketCategory.parent_id).where(TicketCategory.id == cat_id)
        )
        cat_id = parent_row.scalar_one_or_none()
    if rule is None:
        return {
            "category_id": category_id,
            "matched": False,
            "reason": "该分类尚未配置责任路由",
        }
    if not rule.enabled:
        return {
            "category_id": category_id,
            "matched": False,
            "reason": "该分类的责任路由已停用",
        }
    out = {
        "category_id": category_id,
        "matched": True,
        "matched_rule_category_id": matched_category_id,
        "reason": None,
        "dispatcher_skill_group_id": rule.dispatcher_skill_group_id,
        "dispatcher_skill_group_name": rule.dispatcher_skill_group.name if rule.dispatcher_skill_group else None,
        "dispatcher_id": rule.dispatcher_id,
        "dispatcher_name": rule.dispatcher.name if rule.dispatcher else None,
        "handler_skill_group_id": rule.handler_skill_group_id,
        "handler_skill_group_name": rule.handler_skill_group.name if rule.handler_skill_group else None,
        "owner_id": rule.owner_id,
        "owner_name": rule.owner.name if rule.owner else None,
    }
    # 用户停用时不阻断，但提示
    if rule.dispatcher and not rule.dispatcher.is_active:
        out["reason"] = "注意：协调人已停用，请人工指定其他人"
    return out
