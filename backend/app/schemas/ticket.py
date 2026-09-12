"""Pydantic schemas for POC tickets.

枚举与字段严格遵循 docs/poc/00_poc_workflow_development_contract.md。
请求模型一律 `extra="forbid"`：旧客服字段（customer_phone / dispatcher_id /
satisfaction / callback_* 等）会被直接拒绝为 422。
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.domain.poc_workflow import Priority, TicketAction

#: 正式提交时必须填写的创建阶段字段（草稿不受限）
CREATE_REQUIRED_FIELDS: tuple[str, ...] = (
    "title",
    "product_line",
    "customer_name",
    "priority",
    "problem_type",
    "closure_requirement",
    "occurred_at",
    "location",
    "device_info",
    "description",
    "approver_id",
)


class PocRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")


class TicketCreate(PocRequest):
    """新建或保存草稿。草稿允许字段为空，正式提交由服务端校验必填。"""

    is_draft: bool = False
    title: str | None = Field(default=None, max_length=500)
    product_line: str | None = Field(default=None, max_length=100)
    customer_name: str | None = Field(default=None, max_length=100)
    priority: Priority = Priority.P2_NORMAL
    problem_type: str | None = Field(default=None, max_length=100)
    closure_requirement: str | None = None
    occurred_at: datetime | None = None
    location: str | None = Field(default=None, max_length=300)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    device_info: str | None = None
    description: str | None = None
    approver_id: int | None = None


#: 创建阶段可编辑字段（PATCH）
CREATION_EDITABLE_FIELDS: tuple[str, ...] = (
    "title",
    "product_line",
    "customer_name",
    "priority",
    "problem_type",
    "closure_requirement",
    "occurred_at",
    "location",
    "longitude",
    "latitude",
    "device_info",
    "description",
)

#: 闭环计划节点可编辑字段
PLAN_EDITABLE_FIELDS: tuple[str, ...] = (
    "temporary_measure",
    "long_term_measure",
    "planned_completion_at",
)

#: 分析验证节点可编辑字段
ANALYSIS_EDITABLE_FIELDS: tuple[str, ...] = (
    "initial_investigation",
    "root_cause",
    "analysis_report",
)


class TicketUpdate(PocRequest):
    """只允许修改当前节点规定字段。

    显式不提供 state / skill_group_id / subsystem_owner_id / approver_id，
    这些字段只能通过 `POST /tickets/{id}/actions` 变更。
    """

    title: str | None = Field(default=None, max_length=500)
    product_line: str | None = Field(default=None, max_length=100)
    customer_name: str | None = Field(default=None, max_length=100)
    priority: Priority | None = None
    problem_type: str | None = Field(default=None, max_length=100)
    closure_requirement: str | None = None
    occurred_at: datetime | None = None
    location: str | None = Field(default=None, max_length=300)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    device_info: str | None = None
    description: str | None = None

    temporary_measure: str | None = None
    long_term_measure: str | None = None
    planned_completion_at: datetime | None = None

    initial_investigation: str | None = None
    root_cause: str | None = None
    analysis_report: str | None = None


class TicketActionRequest(PocRequest):
    """统一动作请求体。"""

    action: TicketAction
    comment: str | None = Field(default=None, max_length=4000)
    payload: dict[str, Any] = Field(default_factory=dict)
    expected_version: int = Field(..., ge=1, description="详情返回的 state_version")


class TicketAttachmentOut(BaseModel):
    id: int
    ticket_id: int | None = None
    original_filename: str
    content_type: str
    size: int
    stage: str | None = None
    uploader_id: int | None = None
    uploader_name: str | None = None
    download_url: str
    created_at: datetime


class TicketStateLogOut(BaseModel):
    id: int
    action: str | None = None
    from_state: str | None = None
    to_state: str
    operator_id: int | None = None
    operator_name: str | None = None
    operator_roles: list[str] = Field(default_factory=list)
    comment: str | None = None
    payload: dict[str, Any] | None = None
    responsible_role_snapshot: str | None = None
    responsible_user_id_snapshot: int | None = None
    responsible_user_name_snapshot: str | None = None
    state_version: int | None = None
    created_at: datetime


class TicketBrief(BaseModel):
    id: int
    number: str | None = None
    title: str | None = None
    product_line: str | None = None
    customer_name: str | None = None
    priority: str
    problem_type: str | None = None
    state: str
    state_version: int
    is_draft: bool = False
    return_to_state: str | None = None

    current_responsible_role: str | None = None
    current_responsible_user_id: int | None = None
    current_responsible_user_name: str | None = None

    creator_id: int | None = None
    creator_name: str | None = None
    creator_department: str | None = None
    approver_id: int | None = None
    approver_name: str | None = None
    skill_group_id: int | None = None
    skill_group_name: str | None = None
    subsystem_owner_id: int | None = None
    subsystem_owner_name: str | None = None

    planned_completion_at: datetime | None = None
    actual_completion_at: datetime | None = None
    is_overdue: bool = False
    verification_status: str | None = None
    defect_id: str | None = None

    created_at: datetime
    updated_at: datetime


class TicketDetail(TicketBrief):
    closure_requirement: str | None = None
    occurred_at: datetime | None = None
    location: str | None = None
    longitude: float | None = None
    latitude: float | None = None
    device_info: str | None = None
    description: str | None = None

    confirmation_comment: str | None = None
    acceptance_comment: str | None = None
    temporary_measure: str | None = None
    long_term_measure: str | None = None
    plan_confirmation_comment: str | None = None
    initial_investigation: str | None = None
    root_cause: str | None = None
    analysis_report: str | None = None
    verification_conclusion: str | None = None
    quality_review_result: str | None = None
    defect_repository_path: str | None = None
    defect_registered_at: datetime | None = None
    defect_registered_by_id: int | None = None
    defect_registered_by_name: str | None = None
    closed_at: datetime | None = None

    allowed_actions: list[str] = Field(default_factory=list)
    attachments: list[TicketAttachmentOut] = Field(default_factory=list)
    state_logs: list[TicketStateLogOut] = Field(default_factory=list)


class PaginatedTickets(BaseModel):
    data: list[TicketBrief]
    pagination: dict


class DuplicateWarning(BaseModel):
    duplicate_detected: bool = False
    duplicate_tickets: list[dict] = Field(default_factory=list)


class TicketCreateResponse(BaseModel):
    data: TicketDetail
    warnings: DuplicateWarning | None = None


class DraftSubmitRequest(PocRequest):
    """草稿正式提交。允许提交时补齐创建阶段字段。"""

    title: str | None = Field(default=None, max_length=500)
    product_line: str | None = Field(default=None, max_length=100)
    customer_name: str | None = Field(default=None, max_length=100)
    priority: Priority | None = None
    problem_type: str | None = Field(default=None, max_length=100)
    closure_requirement: str | None = None
    occurred_at: datetime | None = None
    location: str | None = Field(default=None, max_length=300)
    longitude: Decimal | None = Field(default=None, ge=-180, le=180)
    latitude: Decimal | None = Field(default=None, ge=-90, le=90)
    device_info: str | None = None
    description: str | None = None
    approver_id: int | None = None
