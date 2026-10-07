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
from app.models.dispatch import DispatchChain


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


class ResponsibilitySlots(NamedTuple):
    """工单全生命周期的责任槽位（由分类静态推导，不依赖运行时历史）。

    工单流程是**创建 → 问题判断 → 流转 → 处理**。客服建单时确认一/二级分类后，
    该分类是否需要后续继续判断、由谁判断，是分类的固有属性，记录在
    ``dispatch_chains``（每个分类一条链，``steps`` 是该分类的处理链）。

    推导方式：从当前分类沿 parent 链上溯，逐层看该分类有没有链：

    - 当前分类**无启用子节点**（叶子，判断已结束）→ 它自己的链是**处理链**：
      ``steps[-1]``（最后一环）是**问题处理部门**（真正干活的），
      ``steps[:-1]``（中间环节）是**流转节点**；祖先的链首构成**问题判断组**
    - 当前分类**有启用子节点**（判断节点，如业务保障/星座大系统）→ 它的链首
      还要继续分诊，计入**问题判断组**，处理部门待分诊确定（None）

    判断组顺序 = 判断先后（根→叶）；流转节点顺序 = 流转先后（近→叶）。

    例：核心网系统(2311) → 判断组[售后, 星座大系统负责人]，流转[]，处理 软件开发组
        套餐变更(2203)   → 判断组[]，流转[市场生态部]，处理 业务支撑组（审核→执行）
        业务保障(2301)   → 判断组[售后]，流转[]，处理 None（待分诊）
        品牌合作(1202)   → 判断组[]，流转[]，处理 品牌传播与大客户
    """

    judgement_departments: tuple[str, ...]
    transit_departments: tuple[str, ...]
    handling_department: str | None


async def _load_categories(db: AsyncSession) -> dict[int, TicketCategory]:
    rows = (await db.execute(select(TicketCategory))).scalars().all()
    return {c.id: c for c in rows}


async def build_responsibility_index(db: AsyncSession) -> dict[int, ResponsibilitySlots]:
    """构建 ``category_id -> ResponsibilitySlots`` 映射。

    分类表和分派链表都极小（数十行），各一次查询后全内存推导，避免逐工单
    递归产生 N+1。与 :func:`build_lineage_index` 共享分类载入结果时请一并调用，
    避免重复查询。
    """
    by_id = await _load_categories(db)
    # 每个分类的处理链（有序）：category_id -> [部门, ...]
    chains: dict[int, list[str]] = {}
    for row in (await db.execute(
        select(DispatchChain).where(DispatchChain.enabled == True)  # noqa: E712
    )).scalars().all():
        depts = [s.get("department_code") for s in (row.steps or []) if s.get("department_code")]
        if depts:
            chains[row.category_id] = depts

    has_active_child: dict[int, bool] = {}
    for c in by_id.values():
        if c.parent_id is not None:
            has_active_child[c.parent_id] = True

    index: dict[int, ResponsibilitySlots] = {}
    for cid in by_id:
        # 近→远上溯（自己 → 父 → 祖）
        is_leaf = not has_active_child.get(cid)
        judgement: list[str] = []  # 判断组，收集时近→远，最后反转
        transit: list[str] = []  # 流转节点，收集时近→远
        handling: str | None = None
        cur: TicketCategory | None = by_id.get(cid)
        seen: set[int] = set()
        first = True
        while cur is not None and cur.id not in seen:
            seen.add(cur.id)
            steps = chains.get(cur.id) or []
            if steps:
                if first and is_leaf:
                    # 叶子：自己这条链的最后一环才是处理部门，前面的是流转节点
                    handling = steps[-1]
                    transit.extend(steps[:-1])
                else:
                    # 判断节点：链首=判断组一环，其余环节=流转节点
                    judgement.append(steps[0])
                    transit.extend(steps[1:])
            first = False
            cur = by_id.get(cur.parent_id) if cur.parent_id is not None else None
        index[cid] = ResponsibilitySlots(
            judgement_departments=tuple(reversed(judgement)),
            transit_departments=tuple(reversed(transit)),
            handling_department=handling,
        )
    return index


async def build_lineage_index(db: AsyncSession) -> dict[int, CategoryLineage]:
    """一次性载入全部分类，构建 ``category_id -> CategoryLineage`` 映射。

    必须沿 parent 链走到根，不能只取一层 ``parent``：分类树是任意深度的
    （V2 树有 4 层，如 客户服务/业务保障/星座大系统/核心网系统），只取一层
    会把二级节点（业务保障）误当成一级。

    分类表极小（数十行），一次查询换掉逐工单递归，避免列表页 N+1。
    """
    by_id = await _load_categories(db)
    index: dict[int, CategoryLineage] = {}
    for c in by_id.values():
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
