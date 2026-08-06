"""User model."""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="agent")
    group_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("groups.id", ondelete="SET NULL"))
    is_group_leader: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # 会话版本号：每次登录 +1，旧会话的 JWT（版本落后）随之失效，
    # 实现"一个账号同时只能一人在线"（后登录者顶掉前者）
    token_version: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    dingtalk_id: Mapped[str | None] = mapped_column(String(100))
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=func.now(), onupdate=func.now())

    # relationships
    group = relationship("Group", back_populates="users", lazy="selectin")
    skill_groups = relationship("SkillGroup", secondary="user_skill_groups", back_populates="users", lazy="selectin")
