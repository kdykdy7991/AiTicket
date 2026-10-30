"""Ticket, Article, TicketStateLog models."""

from datetime import datetime

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text, func
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
    industry: Mapped[str | None] = mapped_column(String(50))
    customer_email: Mapped[str | None] = mapped_column(String(255))
    satellite_number: Mapped[str | None] = mapped_column(String(100))
    is_opportunity: Mapped[bool | None] = mapped_column(Boolean)
    expected_result: Mapped[str | None] = mapped_column(String(50))
    fault_occurred_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    fault_recurrence: Mapped[str | None] = mapped_column(String(30))
    fault_location: Mapped[str | None] = mapped_column(String(255))
    is_batch_fault: Mapped[bool | None] = mapped_column(Boolean)
    customer_level: Mapped[str | None] = mapped_column(String(20), default="normal")
    device_sn: Mapped[str | None] = mapped_column(String(100))
    region_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("regions.id", ondelete="SET NULL"))
    region_name: Mapped[str | None] = mapped_column(String(200))
    symptom: Mapped[str | None] = mapped_column(Text)

    # 分类与归属
    category_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("ticket_categories.id", ondelete="SET NULL"))
    group_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("groups.id", ondelete="SET NULL"))
    skill_group_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("skill_groups.id", ondelete="SET NULL"))
    handler_skill_group_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("skill_groups.id", ondelete="SET NULL"), nullable=True
    )  # 专业处理部门（与 skill_group_id=协调部门 区分）
    owner_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    creator_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="RESTRICT"), nullable=False)
    first_owner_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))
    dispatcher_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))  # 部门对接人

    # 分派链快照（分派设计 V0.21 §3）：建单/分诊时从 dispatch_chains 展开写入，
    # 后续按快照推进——链规则改动不影响在途工单。
    # steps 与 dispatch_chains.steps 同构 [{"order":1,"department_code":"售后"},...]
    # index = 当前步骤（0 起）；两者同时为 null 表示该单不走链（旧路由/即时办结）。
    dispatch_chain_steps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    dispatch_step_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Snapshots taken before entering each new workflow node. A return pops one.
    return_checkpoints: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    legacy_return_cursor_log_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)

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

    # 暂缓（on_hold）。与 SLA 完全无关：这里只记录「预计什么时候恢复继续处理」，
    # 不是 deadline，也不参与任何计时/超时判定。
    hold_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))  # 预计恢复时间
    # 预计恢复时间提醒的去重标记：命中并发送过一次提醒后落值，resume 时清空，
    # 因此每一轮暂缓最多提醒一次。
    hold_reminded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    # 结案
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_duration_minutes: Mapped[int | None] = mapped_column(Integer)

    # 解决信息
    resolved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    resolution: Mapped[str | None] = mapped_column(Text)
    # 根本原因 / 解决办法（Phase 7 结构化处理）
    root_cause: Mapped[str | None] = mapped_column(Text)
    solution: Mapped[str | None] = mapped_column(Text)

    # 投诉级别（Phase 8）：仅对服务投诉类工单有意义。一般/重要/重大 三档。
    # 非投诉工单保持 null，不影响既有逻辑。
    complaint_level: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # 退回：记录应退回给哪位处理人（pending/open 退回给 dispatcher，resolved 退回给 owner）
    returned_to_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="SET NULL"))

    # 回访 / 归档
    # 是否「要求回访」：由分类规则在建单/分诊时确定并落库（callback_policy），
    # 与 is_callbacked（实际是否完成回访）是两个独立事实，禁止互相同步。
    # 存量行保持原值；新建工单一律显式赋值，这里只兜底为「不要求」。
    callback_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    callback_details: Mapped[str | None] = mapped_column(Text)
    archive_notes: Mapped[str | None] = mapped_column(Text)
    is_callbacked: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 追加信息
    has_addition: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 退回历史标记
    has_returned: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # 回访满意度：仅当 is_callbacked=true 时填写
    # 值：'satisfied' / 'average' / 'dissatisfied' / 'unrated'，未回访时为 null
    satisfaction: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # V0.15 数值评分；独立于历史四档 satisfaction，不参与其统计或归档阈值。
    customer_satisfaction_score: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # 不满意原因（设计 §8.2 #9：回访双分支"收集不满意原因"）：
    # v4 不认可或历史 satisfaction=dissatisfied 时必填；退回重开后保留，
    # 新一轮回访若为非不满意则随之清空。
    unsatisfied_reason: Mapped[str | None] = mapped_column(Text)

    # 关单结果（closure 节点，v1）：受控枚举，面向关单口径统计。
    # 值域由已发布表单下发，不在代码里枚举业务语义：
    # recovered / explained / customer_abandoned / terminal_hardware_damage /
    # environment_obstruction / other。历史工单为 null。
    closure_result: Mapped[str | None] = mapped_column(String(30), nullable=True)

    # 客户是否认可（closure 节点，v1）：是否认可本次处理结果。
    # null = 尚未记录（历史工单）；与 satisfaction 分档是两个独立事实。
    customer_recognized: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())

    # relationships
    articles = relationship("Article", back_populates="ticket", lazy="noload", cascade="all, delete-orphan")
    state_logs = relationship("TicketStateLog", back_populates="ticket", lazy="noload", cascade="all, delete-orphan")
    sla_rounds = relationship("SLARound", lazy="selectin", order_by="SLARound.sequence", cascade="all, delete-orphan")
    owner = relationship("User", foreign_keys=[owner_id], lazy="selectin")
    creator = relationship("User", foreign_keys=[creator_id], lazy="selectin")
    dispatcher = relationship("User", foreign_keys=[dispatcher_id], lazy="selectin")
    first_owner = relationship("User", foreign_keys=[first_owner_id], lazy="selectin")
    returned_to_user = relationship("User", foreign_keys=[returned_to_user_id], lazy="selectin")
    category = relationship("TicketCategory", lazy="selectin")
    group = relationship("Group", lazy="selectin")
    skill_group = relationship("SkillGroup", foreign_keys=[skill_group_id], lazy="selectin")
    handler_skill_group = relationship(
        "SkillGroup", foreign_keys=[handler_skill_group_id], lazy="selectin"
    )


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
    hold_until_snapshot: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Flow Log 动作类型：由 (from_state, to_state) 经 state_machine.action_for 推导
    # （create/dispatch/hold/resume/resolve/reopen/return/resubmit/archive/cancel/
    #  instant_resolve）。历史日志为 NULL（不回填）。
    action_type: Mapped[str | None] = mapped_column(String(30))
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
