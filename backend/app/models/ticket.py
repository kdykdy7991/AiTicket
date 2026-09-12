"""POC 工单、附件、流程日志模型。

本模块只保留 POC 质量问题闭环需要的字段。
旧客服工单列（channel / customer_phone / owner_id / dispatcher_id / callback_* /
satisfaction / sla_* 等）仍在数据库中，但已从 ORM 移除，属于 migration-only 历史列，
任何业务代码都不得再读写。
"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Ticket(Base):
    """POC 质量问题工单。"""

    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    number: Mapped[str | None] = mapped_column(String(20), unique=True)
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # ── 创建阶段字段 ──────────────────────────────────────
    title: Mapped[str | None] = mapped_column(String(500))
    product_line: Mapped[str | None] = mapped_column(String(100))
    customer_name: Mapped[str | None] = mapped_column(String(100))
    problem_type: Mapped[str | None] = mapped_column(String(100))
    closure_requirement: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="p2_normal")
    occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    location: Mapped[str | None] = mapped_column(String(300))
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    device_info: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")
    approver_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    creator_department: Mapped[str | None] = mapped_column(String(100))

    # ── 后续阶段字段 ──────────────────────────────────────
    confirmation_comment: Mapped[str | None] = mapped_column(Text)
    subsystem_owner_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    acceptance_comment: Mapped[str | None] = mapped_column(Text)
    temporary_measure: Mapped[str | None] = mapped_column(Text)
    long_term_measure: Mapped[str | None] = mapped_column(Text)
    planned_completion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    plan_confirmation_comment: Mapped[str | None] = mapped_column(Text)
    initial_investigation: Mapped[str | None] = mapped_column(Text)
    root_cause: Mapped[str | None] = mapped_column(Text)
    analysis_report: Mapped[str | None] = mapped_column(Text)
    actual_completion_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    verification_status: Mapped[str | None] = mapped_column(String(30))
    verification_conclusion: Mapped[str | None] = mapped_column(Text)
    quality_review_result: Mapped[str | None] = mapped_column(Text)
    defect_id: Mapped[str | None] = mapped_column(String(100))
    defect_repository_path: Mapped[str | None] = mapped_column(String(1000))
    defect_registered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    defect_registered_by_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )

    # ── 流程控制 ──────────────────────────────────────────
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    state_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default="1"
    )
    return_to_state: Mapped[str | None] = mapped_column(String(40))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # ── 归属 ──────────────────────────────────────────────
    skill_group_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("skill_groups.id", ondelete="SET NULL")
    )
    creator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )

    #: migration-only：非空表示这是迁移前的旧客服工单，业务代码必须过滤掉
    legacy_state: Mapped[str | None] = mapped_column(String(30))

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now()
    )

    # relationships
    creator = relationship("User", foreign_keys=[creator_id], lazy="selectin")
    approver = relationship("User", foreign_keys=[approver_id], lazy="selectin")
    subsystem_owner = relationship("User", foreign_keys=[subsystem_owner_id], lazy="selectin")
    defect_registered_by = relationship(
        "User", foreign_keys=[defect_registered_by_id], lazy="selectin"
    )
    skill_group = relationship("SkillGroup", lazy="selectin")
    state_logs = relationship(
        "TicketStateLog",
        back_populates="ticket",
        lazy="noload",
        cascade="all, delete-orphan",
        order_by="TicketStateLog.id",
    )
    attachments = relationship(
        "TicketAttachment",
        back_populates="ticket",
        lazy="noload",
        cascade="all, delete-orphan",
        order_by="TicketAttachment.id",
    )


class TicketAttachment(Base):
    """POC 工单附件（复用 article_attachments 表，表内 article_id 为 migration-only 历史列）。"""

    __tablename__ = "article_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    # 注：表中的 article_id 是旧客服沟通记录列，已从 ORM 移除（migration-only），
    # POC 附件一律挂 ticket_id。
    ticket_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("tickets.id", ondelete="CASCADE")
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    stage: Mapped[str | None] = mapped_column(String(40))
    uploader_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )

    ticket = relationship("Ticket", back_populates="attachments")
    uploader = relationship("User", lazy="selectin")


class TicketStateLog(Base):
    """不可变流程日志：记录谁在什么时候把工单从哪个状态推到哪个状态。"""

    __tablename__ = "ticket_state_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False
    )
    from_state: Mapped[str | None] = mapped_column(String(30))
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    operator_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    action: Mapped[str | None] = mapped_column(String(40))
    comment: Mapped[str | None] = mapped_column(Text)
    reason: Mapped[str | None] = mapped_column(Text)
    payload_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    state_version: Mapped[int | None] = mapped_column(Integer)
    responsible_role_snapshot: Mapped[str | None] = mapped_column(String(20))
    responsible_user_id_snapshot: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )

    # migration-only 旧快照列：保留在数据库，ORM 不再使用
    ticket = relationship("Ticket", back_populates="state_logs")
    operator = relationship("User", foreign_keys=[operator_id], lazy="selectin")
    responsible_user_snapshot = relationship(
        "User", foreign_keys=[responsible_user_id_snapshot], lazy="selectin"
    )
