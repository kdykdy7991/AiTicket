"""Category tree helpers (recursive depth, ancestor lookup, cycle detection).

Phase 1: TicketCategory supports arbitrary depth.
The `level` column is kept for backward compatibility but is now a derived
attribute computed from the parent chain, not a hard constraint.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import TicketCategory


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
