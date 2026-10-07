"""Category tree helpers (recursive depth, ancestor lookup, cycle detection).

Phase 1: TicketCategory supports arbitrary depth.
The `level` column is kept for backward compatibility but is now a derived
attribute computed from the parent chain, not a hard constraint.
"""

from __future__ import annotations

from typing import NamedTuple

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import TicketCategory


class CategoryLineage(NamedTuple):
    """工单分类的派生血缘。

    工单只存`category_id`（分诊会把它细化到任意深度），所以 L1/L2/路径
    全都是沿parent 链派生的，不落库。

    - l1: 根节点（一级分类）
    - l2: 根节点的直接子级（二级分类）
    - path: root → leaf 完整链，用于界面展示全路径
    """

    l1: TicketCategory | None
    l2: TicketCategory | None
    path: tuple[TicketCategory, ...]


async def build_lineage_index(db: AsyncSession) -> dict[int, CategoryLineage]:
    """一次性载入全部分类，构建 ``category_id -> CategoryLineage`` 映射。

    必须沿 parent 链走到根，不能只取一层 ``parent``：分类树是任意深度的
    （V2 树有 4 层，如 客户服务/业务保障/星座大系统/核心网系统），只取一层
    会把二级节点（业务保障）误当成一级。

    分类表极小（数十行），一次查询换掉逐工单递归，避免列表页 N+1。
    """
    rows = (await db.execute(select(TicketCategory))).scalars().all()
    by_id = {c.id: c for c in rows}
    index: dict[int, CategoryLineage] = {}
    for c in rows:
        chain: list[TicketCategory] = []
        cur: TicketCategory | None = c
        seen: set[int] = set()
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            chain.append(cur)
            cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None
        chain.reverse()  # 现在是 root → leaf
        index[c.id] = CategoryLineage(
            l1=chain[0] if chain else None,
            l2=chain[1] if len(chain) > 1 else None,
            path=tuple(chain),
        )
    return index


async def get_category_by_id(db: AsyncSession, category_id: int | None) -> TicketCategory | None:
    if category_id is None:
        return None
    result = await db.execute(select(TicketCategory).where(TicketCategory.id == category_id))
    return result.scalar_one_or_none()


async def compute_level(db: AsyncSession, category: TicketCategory) -> int:
    """Walk up the parent chain to compute the depth (1-based)."""
    level = 1
    cursor = category
    visited: set[int] = set()
    while cursor.parent_id is not None:
        if cursor.id in visited:
            # Defensive: should not happen post-validation, but break the loop.
            break
        visited.add(cursor.id)
        parent = await get_category_by_id(db, cursor.parent_id)
        if parent is None:
            break
        cursor = parent
        level += 1
    return level


async def is_descendant(
    db: AsyncSession, ancestor_id: int, candidate_id: int
) -> bool:
    """Check whether `candidate_id` is a descendant (or equal to) `ancestor_id`.

    Used for cycle detection: setting node X's parent to Y is invalid if Y is
    X itself or one of X's descendants.
    """
    if ancestor_id == candidate_id:
        return True
    queue: list[int] = [ancestor_id]
    seen: set[int] = set()
    while queue:
        current = queue.pop(0)
        if current in seen:
            continue
        seen.add(current)
        result = await db.execute(
            select(TicketCategory.id).where(TicketCategory.parent_id == current)
        )
        for (child_id,) in result.all():
            if child_id == candidate_id:
                return True
            queue.append(child_id)
    return False


async def build_category_path(
    db: AsyncSession, category_id: int | None
) -> list[TicketCategory]:
    """Return ancestor chain from root → leaf (inclusive). Empty list if id is None."""
    chain: list[TicketCategory] = []
    cursor = await get_category_by_id(db, category_id)
    while cursor is not None:
        chain.append(cursor)
        if cursor.parent_id is None:
            break
        cursor = await get_category_by_id(db, cursor.parent_id)
    chain.reverse()
    return chain


async def would_create_cycle(
    db: AsyncSession, node_id: int, new_parent_id: int | None
) -> bool:
    """If `node_id`'s parent becomes `new_parent_id`, would that introduce a cycle?"""
    if new_parent_id is None:
        return False
    if new_parent_id == node_id:
        return True
    return await is_descendant(db, node_id, new_parent_id)
