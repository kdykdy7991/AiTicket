"""Dispatch chains — 分类 → 部门代称链（设计见 docs/ticket_dispatch_design.md §3 表A）.

- 每分类一条链（category_id UNIQUE）：分类树本身就是路由键，
  没有 condition、没有 priority。
- steps 为 JSON 数组，元素形如 {"order": 1, "department_code": "售后"}，
  只存部门代称（字符串），人员映射由 department_member（user_skill_groups）维护。
- enabled=false 时运行侧应视为无链（回退人工分派）。

与 CategoryRoutingRule（旧表）双轨并存，迁移完成后旧表退居只读/下线。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, DateTime, ForeignKey, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class DispatchChain(Base):
    __tablename__ = "dispatch_chains"
    __table_args__ = (
        UniqueConstraint("category_id", name="uq_dispatch_chain_category"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 适用分类（任意层级）。UNIQUE —— 一个分类一条链。
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ticket_categories.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 部门链（顺序执行）：[{"order": 1, "department_code": "售后"}, ...]
    steps: Mapped[list] = mapped_column(JSON, nullable=False)

    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=func.true(),
    )
    note: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=func.now(), onupdate=func.now(),
    )

    category = relationship("TicketCategory", lazy="selectin")
