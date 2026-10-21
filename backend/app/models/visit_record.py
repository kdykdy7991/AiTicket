"""来访记录；独立于工单，不触发工单流转和统计。"""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class VisitRecord(Base):
    __tablename__ = "visit_records"
    __table_args__ = (UniqueConstraint("source_sheet", "source_row", name="uq_visit_records_source"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source_sheet: Mapped[str | None] = mapped_column(String(80))
    source_row: Mapped[int | None] = mapped_column(Integer)
    contact_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    contact_number: Mapped[str | None] = mapped_column(String(100), index=True)
    customer_name: Mapped[str | None] = mapped_column(String(100))
    service_agent: Mapped[str | None] = mapped_column(String(100))
    channel: Mapped[str] = mapped_column(String(40), nullable=False)
    category_l1: Mapped[str | None] = mapped_column(String(100), index=True)
    category_l2: Mapped[str | None] = mapped_column(String(100))
    registered_ticket: Mapped[bool | None] = mapped_column()
    fields: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
