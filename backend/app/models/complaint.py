"""Complaint routing configuration (Phase 8).

Per-level escalation policy for service-complaint tickets:
- 一般 (general): default SLA, agent role required
- 重要 (important): 25% SLA cut, manager role required
- 重大 (critical): 50% SLA cut, admin role required

Historical tickets stay NULL; no automatic backfill is performed.
"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Float, ForeignKey, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class ComplaintEscalationPolicy(Base):
    __tablename__ = "complaint_escalation_policies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    complaint_level: Mapped[str] = mapped_column(String(20), nullable=False, unique=True)
    notify_skill_group_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("skill_groups.id", ondelete="SET NULL"), nullable=True
    )
    sla_resolution_multiplier: Mapped[float] = mapped_column(Float, nullable=False, default=1.0)
    required_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # 升级链（设计 §5.2 / §8.2 #6）：动态角色序列，role 不绑具体人。
    # 一般 = NULL（走 dispatch_chain → 值班组）；重要 = [部门负责人]；
    # 重大 = [部门负责人 → 分管领导]。steps 同构 dispatch_chains.steps 的 order 语义。
    escalation_chain: Mapped[list | None] = mapped_column(JSON, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )

    notify_skill_group = relationship("SkillGroup", lazy="selectin")

    __table_args__ = (
        # Re-affirm UNIQUE for the table metadata (already on column).
    )