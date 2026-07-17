"""SLAPolicy model."""

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SLAPolicy(Base):
    __tablename__ = "sla_policies"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    skill_group_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("skill_groups.id", ondelete="CASCADE"))
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    first_response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    solution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())
