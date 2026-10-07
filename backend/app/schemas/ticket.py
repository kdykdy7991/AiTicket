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
    handler_skill_group_id: int | None = None  # 专业处理部门（Phase 4 新增，可由路由规则自动填）
    dispatcher_id: int | None = None  # 部门对接人（正式提交必填）
    is_duplicate: bool = False
    duplicate_reason: str | None = None
    is_draft: bool = False
    # Phase 7: 结构化处理
    root_cause: str | None = None
    solution: str | None = None
    # Phase 8: 投诉级别（仅对服务投诉类工单有意义）
    # 取值: "一般" / "重要" / "重大"
    complaint_level: str | None = None
    # Phase 6: 即时办结咨询
    # 走完整表单，但建单后直接进入 archived（终态），
    # 工单仍然有 number / SLA 记录与 state_log 审计
    is_instant_resolve: bool = False
    instant_resolution: str | None = None  # 即时办结的处理记录 / 答案摘要


class TicketUpdate(BaseModel):
    state: str | None = None
    priority: str | None = None
    owner_id: int | None = None
    group_id: int | None = None
    skill_group_id: int | None = None
    handler_skill_group_id: int | None = None
    dispatcher_id: int | None = None
    reason: str | None = None  # for state transitions requiring a reason
    hold_until: str | None = None  # 暂缓到的时间（ISO date），暂缓时填写
    callback_details: str | None = None  # 回访详情
    archive_notes: str | None = None  # 归档备注
    is_callbacked: bool | None = None  # 是否已回访
    callback_required: bool | None = None  # 是否需要回访（false=无需回访）
    satisfaction: str | None = None  # 回访满意度：'satisfied' / 'average' / 'dissatisfied' / 'unrated'，仅当 is_callbacked=true 时填写
    unsatisfied_reason: str | None = None  # 不满意原因（satisfaction=dissatisfied 时必填，设计 §8.2 #9）
    root_cause: str | None = None  # 根本原因
    solution: str | None = None    # 解决办法
    complaint_level: str | None = None  # 投诉级别


class TicketBatchUpdate(BaseModel):
    ticket_ids: list[int] = Field(..., min_length=1, max_length=100)
    updates: TicketUpdate


class TicketCancel(BaseModel):
    reason: str | None = None


class TicketRefine(BaseModel):
    """分诊请求：把工单分类细化到当前分类的直下级。"""
    category_id: int


class TicketTransfer(BaseModel):
    """转派请求（多步链）：本步完成，推进到链的下一部门。"""
    reason: str | None = None  # 留空自动填"本步完成，转派「下一部门」"


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
    handler_skill_group_id: int | None = None
    handler_skill_group_name: str | None = None
    owner_id: int | None = None
    owner_name: str | None = None
    dispatcher_id: int | None = None
    dispatcher_name: str | None = None
    category_id: int | None = None
    category_name: str | None = None
    # 以下均为派生值（工单只存 category_id）：L1=根节点、L2=根的直接子级
    category_l1_id: int | None = None
    category_l1_name: str | None = None
    category_l2_id: int | None = None
    category_l2_name: str | None = None
    # 完整路径 root→leaf，如 "客户服务 / 业务保障 / 星座大系统 / 核心网系统"
    category_path: str | None = None
    # 责任槽位（由分类静态推导，见 category_utils.ResponsibilitySlots）
    # judgement_departments: 问题判断组，按判断先后排序；空=客服组建单时已判断完
    judgement_departments: list[str] = []
    # handling_department: 问题处理部门；判断节点未分诊时为 None
    handling_department: str | None = None
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
    # 终态操作人：哪个用户执行了 resolved→archived 或 *→cancelled 流转
    # 从 state_logs 查询得到，不落库到 tickets 表（避免与 state_log 漂移）
    archived_by_id: int | None = None
    archived_by_name: str | None = None
    cancelled_by_id: int | None = None
    cancelled_by_name: str | None = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AllowedAction(BaseModel):
    """后端生成的状态动作元数据——前端按钮的唯一渲染依据。"""
    action: str            # dispatch/return/cancel/resolve/hold/resume/reopen/resubmit/archive
    target_state: str      # 执行该动作后的目标状态（已含业务约束改写）
    requires_reason: bool = False   # 点击后必须填写原因
    requires_owner: bool = False    # 动作前置要求：分派时须先选择处理人
    label: str = ""        # 中文按钮文案


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
    satisfaction: str | None = None  # 回访满意度：'satisfied' / 'average' / 'dissatisfied' / 'unrated'
    unsatisfied_reason: str | None = None  # 不满意原因（dissatisfied 时非空）
    is_callbacked: bool = False
    root_cause: str | None = None  # 根本原因
    solution: str | None = None    # 解决办法
    complaint_level: str | None = None  # 投诉级别

    # V0.86：后端生成的动作/能力元数据（前端只渲染，不再自算业务规则）
    allowed_actions: list[AllowedAction] = []   # 当前用户在当前状态可执行的状态动作
    is_terminal: bool = False                   # 终态（archived/cancelled）
    can_reply: bool = False                     # 可提交处理说明（会触发 →resolved 流转）
    can_addition: bool = False                  # 可追加说明
    can_remind: bool = False                    # 可催办（且尚未催办过）

    # 分派链快照（V0.21）：steps 同构 dispatch_chains.steps；index=当前步骤（0 起）；
    # null = 不走链（旧路由/即时办结）。前端渲染链进度与转派按钮用。
    dispatch_chain_steps: list | None = None
    dispatch_step_index: int | None = None

    # 分诊能力位（V0.21 §2）：判断人把分类细化一级的入口元数据
    can_refine: bool = False
    refine_options: list[dict] = []              # [{"id","name","level"}] 下级分类
    refine_denied_reason: str | None = None      # 无权/不可分诊的原因（前端提示用）

    model_config = {"from_attributes": True}


class PaginatedTickets(BaseModel):
    data: list[TicketBrief]
    pagination: dict


class DuplicateWarning(BaseModel):
    duplicate_detected: bool = False
    duplicate_tickets: list[dict] = []
    # Phase 5: 工单创建后告诉前端路由规则填了哪些字段 / 是否有警告
    # 例如: "已根据路由规则自动分配协调人/专业部"
    auto_match_warning: str | None = None


class TicketCreateResponse(BaseModel):
    data: TicketDetail
    warnings: DuplicateWarning | None = None
