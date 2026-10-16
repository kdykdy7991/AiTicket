"""「是否需要回访」由分类规则决定，与「是否已完成回访」严格分离。

规则来源是分类表上的一个布尔列（:attr:`TicketCategory.requires_callback`），
语义为 **自身或任一祖先为 True**：

- 标在「业务保障」一级 → 它的所有后代分类（含任意深度）都要求回访；
- 标在「业务运营 / 套餐变更」二级 → 只覆盖该分支及其后代；
- 其余分类默认 False。

业务代码不硬编码分类 ID；要调整规则只改分类配置。

两个字段的边界（不要再次合并它们）：

- ``TicketCategory.requires_callback`` / ``Ticket.callback_required``
  —— 根据业务规则，**这张工单是否要求回访**；
- ``Ticket.is_callbacked`` —— **实际是否已经完成回访**。

取值时机：工单分类每次变化时重算并落库（建单、草稿修改、分诊细化、退回后
重新提交），之后不再随配置变化而改变——在途工单的分类事实已经固定，
处理阶段分类不可改，因此该值天然稳定；这也意味着事后修改分类规则不会
追溯改写在途工单。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import TicketCategory
from app.models.ticket import Ticket


async def resolve_callback_required(db: AsyncSession, category_id: int | None) -> bool:
    """分类自身或任一祖先要求回访 → True。无分类返回 False。"""
    if category_id is None:
        return False
    current_id: int | None = category_id
    seen: set[int] = set()
    while current_id is not None and current_id not in seen:
        seen.add(current_id)
        category = await db.get(TicketCategory, current_id)
        if category is None:
            return False
        if category.requires_callback:
            return True
        current_id = category.parent_id
    return False


async def apply_callback_rule(db: AsyncSession, ticket: Ticket) -> None:
    """按工单当前分类重算并写 ``ticket.callback_required``。

    所有「分类刚刚发生变化」的入口都调它，判断只在这一处实现。
    """
    ticket.callback_required = await resolve_callback_required(db, ticket.category_id)


async def callback_rule_index(db: AsyncSession) -> dict[int, bool]:
    """一次性构建 ``category_id -> requires_callback``（供列表/统计复用）。"""
    rows = (await db.execute(select(TicketCategory))).scalars().all()
    by_id = {row.id: row for row in rows}
    index: dict[int, bool] = {}
    for row in rows:
        required = False
        current: TicketCategory | None = row
        seen: set[int] = set()
        while current is not None and current.id not in seen:
            seen.add(current.id)
            if current.requires_callback:
                required = True
                break
            current = by_id.get(current.parent_id) if current.parent_id is not None else None
        index[row.id] = required
    return index
