"""User and UserRole models.

一个用户可以拥有多个业务角色（`user_roles` 关联表），权限取各角色并集。
"""

from datetime import datetime, timezone

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.domain.poc_workflow import ALL_ROLES, BusinessRole

_ROLE_ORDER = {role.value: index for index, role in enumerate(ALL_ROLES)}


class UserRole(Base):
    """用户与业务角色的关联。"""

    __tablename__ = "user_roles"

    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    role: Mapped[str] = mapped_column(String(20), primary_key=True)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(20))
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
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
    role_links = relationship(
        "UserRole",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="UserRole.role",
    )

    # ── 多角色 ────────────────────────────────────────────
    @property
    def roles(self) -> list[str]:
        """按契约固定顺序返回角色编码列表。"""
        return sorted(
            (link.role for link in self.role_links),
            key=lambda role: _ROLE_ORDER.get(role, len(_ROLE_ORDER)),
        )

    def has_role(self, *roles: str | BusinessRole) -> bool:
        """是否拥有其中任一角色。"""
        owned = {link.role for link in self.role_links}
        return any(
            (role.value if isinstance(role, BusinessRole) else role) in owned
            for role in roles
        )

    @property
    def is_admin(self) -> bool:
        return self.has_role(BusinessRole.ADMIN)

    def set_roles(self, roles: list[str | BusinessRole]) -> None:
        """全量替换角色集合（按契约顺序去重）。

        就地增删而不是整体赋值：新建对象上赋值会触发 SQLAlchemy 的
        集合懒加载，在异步会话里会抛 MissingGreenlet。
        """
        seen: list[str] = []
        for role in roles:
            value = role.value if isinstance(role, BusinessRole) else role
            if value not in seen:
                seen.append(value)
        seen.sort(key=lambda role: _ROLE_ORDER.get(role, len(_ROLE_ORDER)))

        for link in list(self.role_links):
            if link.role not in seen:
                self.role_links.remove(link)
        owned = {link.role for link in self.role_links}
        for role in seen:
            if role not in owned:
                self.role_links.append(UserRole(role=role))
