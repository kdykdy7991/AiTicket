"""Category routing rules — map a final category to coordinator + professional handler.

Phase 3: configurable rule per category (typically a leaf). Each rule records:
- dispatcher_skill_group_id : coordinator department (现有 skill_group 概念)
- dispatcher_id              : coordinator user (must be in dispatcher_skill_group
                               with UserSkillGroup.is_dispatcher=true)
- handler_skill_group_id     : professional department (owner 归属)
- owner_id                   : default professional handler (must be in handler_skill_group)

A category without a routing rule is allowed; ticket creation falls back to
the manual mode (agent picks coordinator/handler as before).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger, Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship


from app.core.database import Base


class CategoryRoutingRule(Base):
    __tablename__ = "category_routing_rules"
    __table_args__ = (
        UniqueConstraint("category_id", name="uq_routing_category"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)

    # 适用分类（最终叶子分类）。UNIQUE — 一个分类一条默认规则。
    category_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("ticket_categories.id", ondelete="CASCADE"),
        nullable=False,
    )

    # 协调部门 + 协调人
    dispatcher_skill_group_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("skill_groups.id", ondelete="RESTRICT"),
        nullable=False,
    )
    dispatcher_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    # 专业处理部门 + 默认专业处理人（专业处理人可空：硬件故障等待配置的场景）
    handler_skill_group_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("skill_groups.id", ondelete="RESTRICT"),
    )
    owner_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="RESTRICT"),
    )

    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    note: Mapped[str | None] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=func.now(), onupdate=func.now(),
    )

    category = relationship("TicketCategory", lazy="selectin")
    dispatcher_skill_group = relationship(
        "SkillGroup", foreign_keys=[dispatcher_skill_group_id], lazy="selectin"
    )
    handler_skill_group = relationship(
        "SkillGroup", foreign_keys=[handler_skill_group_id], lazy="selectin"
    )
    dispatcher = relationship(
        "User", foreign_keys=[dispatcher_id], lazy="selectin"
    )
    owner = relationship(
        "User", foreign_keys=[owner_id], lazy="selectin"
    )
