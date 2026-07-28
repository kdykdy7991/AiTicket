"""Ticket, Article, TicketStateLog, Reminder models."""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Ticket(Base):
    __tablename__ = "tickets"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    number: Mapped[str | None] = mapped_column(String(20), unique=True)
    title: Mapped[str | None] = mapped_column(String(500), default="工单")
    description: Mapped[str] = mapped_column(Text, nullable=False, default="")

    # 状态与优先级
    state: Mapped[str] = mapped_column(String(30), nullable=False, default="pending")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, default="p4_enterprise")
    channel: Mapped[str] = mapped_column(String(20), nullable=False, default="phone")

    # 客户信息
    customer_type: Mapped[str] = mapped_column(String(20), nullable=False, default="personal")
    customer_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    customer_phone: Mapped[str] = mapped_column(String(20), nullable=False)
    customer_phone_type: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 来电号码类型: mobile / landline
    contact_phone: Mapped[str | None] = mapped_column(String(20))
    customer_company: Mapped[str | None] = mapped_column(String(200))
    customer_level: Mapped[str | None] = mapped_column(String(20), default="normal")
    device_sn: Mapped[str | None] = mapped_column(String(100))
    region_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("regions.id", ondelete="SET NULL"))
    region_name: Mapped[str | None] = mapped_column(String(200))
    symptom: Mapped[str | None] = mapped_column(Text)

    # 分类与归属
    category_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ticket_categories.id", ondelete="SET NULL"))
    group_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("groups.id", ondelete="SET NULL"))
    skill_group_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("skill_groups.id", ondelete="SET NULL"))
    owner_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    creator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    first_owner_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    dispatcher_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))  # 部门对接人

    # 重复/升级
    is_draft: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_escalated: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    duplicate_reason: Mapped[str | None] = mapped_column(Text)
    linked_ticket_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("tickets.id", ondelete="SET NULL"))

    # SLA
    first_response_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    solution_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_response_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    solved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sla_first_response_breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    sla_solution_breached: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 暂缓
    hold_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 暂缓到的时间（选填）

    # 结案
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_duration_minutes: Mapped[int | None] = mapped_column(Integer)

    # 解决信息
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolution: Mapped[str | None] = mapped_column(Text)

    # 退回：记录应退回给哪位处理人（pending/open 退回给 dispatcher，resolved 退回给 owner）
    returned_to_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))

    # 回访 / 归档
    callback_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    callback_details: Mapped[str | None] = mapped_column(Text)
    archive_notes: Mapped[str | None] = mapped_column(Text)
    is_callbacked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 催办
    urged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    urged_by_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))

    # 追加信息
    has_addition: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 退回历史标记
    has_returned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())

    # relationships
    articles = relationship("Article", back_populates="ticket", lazy="noload", cascade="all, delete-orphan")
    state_logs = relationship("TicketStateLog", back_populates="ticket", lazy="noload", cascade="all, delete-orphan")
    reminders = relationship("Reminder", back_populates="ticket", lazy="noload", cascade="all, delete-orphan")
    owner = relationship("User", foreign_keys=[owner_id], lazy="selectin")
    creator = relationship("User", foreign_keys=[creator_id], lazy="selectin")
    dispatcher = relationship("User", foreign_keys=[dispatcher_id], lazy="selectin")
    first_owner = relationship("User", foreign_keys=[first_owner_id], lazy="selectin")
    returned_to_user = relationship("User", foreign_keys=[returned_to_user_id], lazy="selectin")
    urged_by = relationship("User", foreign_keys=[urged_by_id], lazy="selectin")
    category = relationship("TicketCategory", lazy="selectin")
    group = relationship("Group", lazy="selectin")
    skill_group = relationship("SkillGroup", lazy="selectin")


class Article(Base):
    __tablename__ = "articles"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    type: Mapped[str] = mapped_column(String(20), nullable=False, default="reply")
    sender_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    subject: Mapped[str | None] = mapped_column(String(500))
    body: Mapped[str] = mapped_column(Text, nullable=False, default="")
    state_key: Mapped[str | None] = mapped_column(String(30))
    append_reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())

    ticket = relationship("Ticket", back_populates="articles")
    sender = relationship("User", lazy="selectin")
    attachments = relationship(
        "ArticleAttachment",
        back_populates="article",
        lazy="selectin",
        cascade="all, delete-orphan",
    )


class ArticleAttachment(Base):
    __tablename__ = "article_attachments"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    article_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("articles.id", ondelete="CASCADE"), nullable=False
    )
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_path: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )

    article = relationship("Article", back_populates="attachments")


class TicketStateLog(Base):
    __tablename__ = "ticket_state_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    from_state: Mapped[str | None] = mapped_column(String(30))
    to_state: Mapped[str] = mapped_column(String(30), nullable=False)
    operator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    duration_minutes: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    # 人员快照：写入 state_log 那一刻工单上的创建者/对接人/处理人。
    # 旧数据回填时是 best-effort（tickets 当前值），新建的 state_log 由 _snapshot_people() 正确填充。
    creator_id_snapshot: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    dispatcher_id_snapshot: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    owner_id_snapshot: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))

    ticket = relationship("Ticket", back_populates="state_logs")
    operator = relationship("User", foreign_keys=[operator_id], lazy="selectin")
    creator_snapshot = relationship("User", foreign_keys=[creator_id_snapshot], lazy="selectin")
    dispatcher_snapshot = relationship("User", foreign_keys=[dispatcher_id_snapshot], lazy="selectin")
    owner_snapshot = relationship("User", foreign_keys=[owner_id_snapshot], lazy="selectin")


class Reminder(Base):
    __tablename__ = "reminders"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False)
    sender_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())

    ticket = relationship("Ticket", back_populates="reminders")
    sender = relationship("User", lazy="selectin")
