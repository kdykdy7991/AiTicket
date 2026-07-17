"""Pydantic schemas for users, groups, categories, regions, SLA."""

from datetime import datetime

from pydantic import BaseModel, Field


# ── User ──────────────────────────────────────────────────

class SkillGroupMembership(BaseModel):
    skill_group_id: int
    is_dispatcher: bool = False


class UserCreate(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    name: str = Field(..., min_length=1, max_length=100)
    phone: str | None = None
    password: str = Field(..., min_length=6)
    role: str = Field(default="agent")
    group_id: int | None = None
    is_group_leader: bool = False
    skill_groups: list[SkillGroupMembership] = Field(default_factory=list)
    dingtalk_id: str | None = None


class UserUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    password: str | None = None
    role: str | None = None
    group_id: int | None = None
    is_group_leader: bool | None = None
    skill_groups: list[SkillGroupMembership] | None = None
    dingtalk_id: str | None = None
    is_active: bool | None = None


class UserOut(BaseModel):
    id: int
    username: str
    name: str
    phone: str | None = None
    role: str
    group_id: int | None = None
    group_name: str | None = None
    is_group_leader: bool = False
    is_active: bool = True
    dingtalk_id: str | None = None
    last_login_at: datetime | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Group ─────────────────────────────────────────────────

class GroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    dingtalk_webhook_url: str | None = None


class GroupOut(BaseModel):
    id: int
    name: str
    dingtalk_webhook_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── SkillGroup ────────────────────────────────────────────

class SkillGroupCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    dingtalk_webhook_url: str | None = None


class SkillGroupOut(BaseModel):
    id: int
    name: str
    dingtalk_webhook_url: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Category ──────────────────────────────────────────────

class CategoryOut(BaseModel):
    id: int
    name: str
    level: int
    parent_id: int | None = None
    children: list["CategoryOut"] = Field(default_factory=list)
    sort_order: int = 0

    model_config = {"from_attributes": True}


class CategoryCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    parent_id: int | None = None
    sort_order: int = 0
    is_active: bool = True


class CategoryUpdate(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=100)
    sort_order: int | None = None
    is_active: bool | None = None


# ── Region ────────────────────────────────────────────────

class RegionOut(BaseModel):
    id: int
    name: str
    level: int
    parent_id: int | None = None
    code: str | None = None
    children: list["RegionOut"] = Field(default_factory=list)
    sort_order: int = 0

    model_config = {"from_attributes": True}


class RegionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    parent_id: int | None = None
    code: str | None = None


# ── SLA Policy ────────────────────────────────────────────

class SLAPolicyCreate(BaseModel):
    skill_group_id: int | None = None
    priority: str
    solution_minutes: int = Field(..., gt=0)


class SLAPolicyOut(BaseModel):
    id: int
    skill_group_id: int | None = None
    skill_group_name: str | None = None
    priority: str
    solution_minutes: int
    created_at: datetime

    model_config = {"from_attributes": True}


# ── State Log ─────────────────────────────────────────────

class StateLogOut(BaseModel):
    id: int
    from_state: str | None = None
    to_state: str
    operator_id: int
    operator_name: str | None = None
    reason: str | None = None
    duration_minutes: int | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Stats ─────────────────────────────────────────────────

class DashboardStats(BaseModel):
    pending_count: int = 0
    open_count: int = 0
    overdue_count: int = 0
    today_created: int = 0
    today_resolved: int = 0
    sla_breach_rate: float = 0.0
    first_contact_resolution_rate: float = 0.0
    avg_resolution_minutes: int | None = None
    by_priority: dict[str, int] = {}
    by_category: dict[str, int] = {}
