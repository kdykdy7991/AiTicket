"""「建单直指派」由分类规则决定。

规则来源是分类表上的一个布尔列（:attr:`TicketCategory.direct_assign`），
语义与「是否需要回访」一致 —— **自身或任一祖先为 True**：

- 标在「客户咨询」一级 → 它的所有后代分类都由建单人直接指派处理人；
- 标在「渠道/代理合作」上 → 只覆盖该分类自己。

业务代码不硬编码分类 ID；要调整规则只改分类配置。

与「是否需要回访」的边界：

- ``requires_callback`` / ``callback_required``
  —— 根据业务规则，**这张工单是否要求回访**；
- ``direct_assign``
  —— **这张工单由谁派**：直指派分类的工单由建单人（客服）在建单时直接
  指定处理人，不经过部门对接人分派。

取值时机：建单与状态流转时按工单当前分类实时读取（不是快照）——
分类规则变了，权限判定跟着变；这一点与 ``callback_required``
（建单时落库、之后不再随配置变化）**有意不同**：直指派只决定
「谁能推进这张单」，不改变工单上已记录的事实。

典型用法::

    if await is_direct_assign_ticket(db, ticket):
        # 该工单免对接人分派：建单人可直接把它指派给处理人
        ...
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import TicketCategory
from app.models.ticket import Ticket


async def resolve_direct_assign(db: AsyncSession, category_id: int | None) -> bool:
    """分类自身或任一祖先标记直指派 → True。无分类返回 False。"""
    if category_id is None:
        return False
    current_id: int | None = category_id
    seen: set[int] = set()
    while current_id is not None and current_id not in seen:
        seen.add(current_id)
        category = await db.get(TicketCategory, current_id)
        if category is None:
            return False
        if category.direct_assign:
            return True
        current_id = category.parent_id
    return False


async def is_direct_assign_ticket(db: AsyncSession, ticket: Ticket) -> bool:
    """工单当前分类是否走直指派通道。"""
    return await resolve_direct_assign(db, ticket.category_id)


async def direct_assign_rule_index(db: AsyncSession) -> dict[int, bool]:
    """一次性构建 ``category_id -> direct_assign``（供建单表单/列表复用）。"""
    rows = (await db.execute(select(TicketCategory))).scalars().all()
    by_id = {row.id: row for row in rows}

    def inherited(category_id: int, seen: set[int] | None = None) -> bool:
        seen = seen or set()
        if category_id in seen:
            return False
        seen.add(category_id)
        row = by_id.get(category_id)
        if row is None:
            return False
        if row.direct_assign:
            return True
        if row.parent_id is None:
            return False
        return inherited(row.parent_id, seen)

    return {row.id: inherited(row.id) for row in rows}


async def assignment_departments(db: AsyncSession, steps: list[dict]) -> list[dict]:
    """Return active department members for each distinct processing department."""
    from datetime import datetime, timezone
    from sqlalchemy import or_
    from app.models.group import SkillGroup, UserSkillGroup
    from app.models.user import User
    now = datetime.now(timezone.utc)
    departments = []
    for code in dict.fromkeys(step['department_code'] for step in steps):
        group = await db.scalar(select(SkillGroup).where(SkillGroup.name == code))
        members = []
        if group:
            members = (await db.execute(select(User).join(UserSkillGroup).where(
                UserSkillGroup.skill_group_id == group.id, User.is_active.is_(True),
                or_(UserSkillGroup.effective_from.is_(None), UserSkillGroup.effective_from <= now),
                or_(UserSkillGroup.effective_to.is_(None), UserSkillGroup.effective_to >= now),
            ).order_by(User.id))).scalars().all()
        departments.append({'department_code': code, 'skill_group_id': group.id if group else None,
                            'handlers': [{'id': u.id, 'name': u.name} for u in members]})
    return departments


async def assign_chain_owners(db: AsyncSession, steps: list[dict], choices: dict[str, int],
                              *, first_owner_id: int | None = None, draft: bool = False) -> list[dict]:
    """Resolve single-member departments, require explicit choices for multiple members."""
    from fastapi import HTTPException
    departments = await assignment_departments(db, steps)
    selected = {}
    for index, department in enumerate(departments):
        code = department['department_code']
        handlers = department['handlers']
        owner = choices.get(code) or (first_owner_id if index == 0 else None)
        if owner is not None and owner not in {u['id'] for u in handlers}:
            raise HTTPException(422, detail=f'处理人不属于责任部门「{code}」的有效成员')
        if owner is None and len(handlers) == 1:
            owner = handlers[0]['id']
        if owner is None and not draft:
            raise HTTPException(422, detail=f'请在建单时选择「{code}」的处理人' if handlers else f'责任部门「{code}」暂无有效处理人')
        selected[code] = owner
    return [{**step, 'assigned_owner_id': selected[step['department_code']]} for step in steps]
