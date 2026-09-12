"""Pydantic schemas for users, skill groups (分系统) and stats."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.domain.poc_workflow import BusinessRole


# ── User ──────────────────────────────────────────────────


class SkillGroupMembership(BaseModel):
    """拥有 subsystem 角色的用户与分系统的关联。"""

    model_config = ConfigDict(extra="forbid")

    skill_group_id: int


class UserCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    username: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = None
    password: str = Field(..., min_length=6)
    #: 一个用户可以拥有多个业务角色，至少一个
    roles: list[BusinessRole] = Field(..., min_length=1)
    skill_groups: list[SkillGroupMembership] = Field(default_factory=list)
    dingtalk_id: str | None = None


class UserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = None
    phone: str | None = None
    password: str | None = None
    #: 全量替换角色集合；None 表示不改
    roles: list[BusinessRole] | None = Field(default=None, min_length=1)
    skill_groups: list[SkillGroupMembership] | None = None
    dingtalk_id: str | None = None
    is_active: bool | None = None


class SkillGroupRef(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    phone: str | None = None
    roles: list[str] = Field(default_factory=list)
    is_active: bool = True
    dingtalk_id: str | None = None
    skill_groups: list[SkillGroupRef] = Field(default_factory=list)
    last_login_at: datetime | None = None
    created_at: datetime


# ── SkillGroup（分系统）────────────────────────────────────


class SkillGroupCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    dingtalk_webhook_url: str | None = None


class SkillGroupOut(BaseModel):
    id: int
    name: str
    dingtalk_webhook_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── State Log ─────────────────────────────────────────────


class StateLogOut(BaseModel):
    id: int
    action: str | None = None
    from_state: str | None = None
    to_state: str
    operator_id: int
    operator_name: str | None = None
    operator_roles: list[str] = Field(default_factory=list)
    comment: str | None = None
    payload: dict | None = None
    responsible_role_snapshot: str | None = None
    state_version: int | None = None
    created_at: datetime


# ── Stats ─────────────────────────────────────────────────


class DashboardStats(BaseModel):
    total: int = 0
    open_count: int = 0
    closed_count: int = 0
    overdue_count: int = 0
    today_created: int = 0
    today_closed: int = 0
    planning_count: int = 0
    pending_approval_count: int = 0
    by_state: dict[str, int] = {}
    by_priority: dict[str, int] = {}
    by_skill_group: dict[str, int] = {}
    by_verification_status: dict[str, int] = {}
