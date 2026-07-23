"""Pydantic schemas for tickets."""

from datetime import datetime

from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    description: str = Field(default="", max_length=10000)
    priority: str = Field(default="p4_enterprise")
    channel: str = Field(default="phone")
    customer_type: str = Field(default="personal")
    customer_name: str | None = Field(default=None, max_length=100)
    customer_phone: str = Field(..., min_length=1, max_length=20)
    customer_phone_type: str | None = Field(default=None, max_length=20)  # 来电号码类型: mobile / landline
    contact_phone: str | None = None
    customer_company: str | None = None
    customer_level: str | None = "normal"
    device_sn: str | None = None
    region_id: int | None = None
    region_name: str | None = None
    category_id: int | None = None
    group_id: int | None = None
    skill_group_id: int | None = None
    dispatcher_id: int | None = None  # 部门对接人（正式提交必填）
    is_duplicate: bool = False
    duplicate_reason: str | None = None
    is_draft: bool = False


class TicketUpdate(BaseModel):
    state: str | None = None
    priority: str | None = None
    owner_id: int | None = None
    group_id: int | None = None
    skill_group_id: int | None = None
    dispatcher_id: int | None = None
    reason: str | None = None  # for state transitions requiring a reason
    hold_until: str | None = None  # 暂缓到的时间（ISO date），暂缓时填写
    callback_details: str | None = None  # 回访详情
    archive_notes: str | None = None  # 归档备注
    is_callbacked: bool | None = None  # 是否已回访


class TicketBatchUpdate(BaseModel):
    ticket_ids: list[int] = Field(..., min_length=1, max_length=100)
    updates: TicketUpdate


class TicketCancel(BaseModel):
    reason: str | None = None


class TicketBrief(BaseModel):
    id: int
    number: str | None = None
    state: str
    priority: str
    channel: str
    customer_type: str
    customer_name: str | None = None
    customer_phone: str
    customer_phone_type: str | None = None
    contact_phone: str | None = None
    skill_group_id: int | None = None
    skill_group_name: str | None = None
    owner_id: int | None = None
    owner_name: str | None = None
    dispatcher_id: int | None = None
    dispatcher_name: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    category_l1_id: int | None = None
    category_l1_name: str | None = None
    category_l2_id: int | None = None
    category_l2_name: str | None = None
    region_name: str | None = None
    is_duplicate: bool = False
    is_draft: bool = False
    is_callbacked: bool = False
    sla_solution_breached: bool = False
    solution_deadline: datetime | None = None
    urged_at: datetime | None = None
    urged_by_id: int | None = None
    urged_by_name: str | None = None
    has_addition: bool = False
    has_returned: bool = False
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TicketDetail(TicketBrief):
    description: str
    customer_company: str | None = None
    customer_level: str | None = None
    device_sn: str | None = None
    region_id: int | None = None
    region_name: str | None = None
    symptom: str | None = None
    creator_id: int | None = None
    creator_name: str | None = None
    first_owner_id: int | None = None
    first_owner_name: str | None = None
    is_escalated: bool = False
    duplicate_reason: str | None = None
    linked_ticket_id: int | None = None
    solved_at: datetime | None = None
    hold_until: datetime | None = None
    closed_at: datetime | None = None
    closed_duration_minutes: int | None = None
    resolved: bool = False
    resolution: str | None = None
    group_id: int | None = None
    group_name: str | None = None
    returned_to_user_id: int | None = None
    returned_to_user_name: str | None = None
    callback_required: bool = True
    callback_details: str | None = None
    archive_notes: str | None = None
    is_callbacked: bool = False

    model_config = {"from_attributes": True}


class PaginatedTickets(BaseModel):
    data: list[TicketBrief]
    pagination: dict


class DuplicateWarning(BaseModel):
    duplicate_detected: bool = False
    duplicate_tickets: list[dict] = []


class TicketCreateResponse(BaseModel):
    data: TicketDetail
    warnings: DuplicateWarning | None = None
