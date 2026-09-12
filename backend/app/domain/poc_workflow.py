"""POC 质量问题闭环领域契约：角色、状态、动作、优先级、验证状态与流转规则。

本模块是后端**唯一**的枚举与流转规则来源。API、Schema、导出、报表都从这里取，
禁止在业务代码里再写一份字符串映射。

契约依据：docs/poc/00_poc_workflow_development_contract.md
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

# ── 业务角色 ───────────────────────────────────────────────


class BusinessRole(StrEnum):
    """固定业务角色，仅允许以下六个编码。历史客服角色编码一律不再接受。"""

    PRESALES = "presales"
    APPROVER = "approver"
    TASKFORCE = "taskforce"
    SUBSYSTEM = "subsystem"
    QUALITY = "quality"
    ADMIN = "admin"


#: 业务责任角色（不含隐藏系统管理员），用于人员选择器与责任人展示
BUSINESS_ROLES: tuple[BusinessRole, ...] = (
    BusinessRole.PRESALES,
    BusinessRole.APPROVER,
    BusinessRole.TASKFORCE,
    BusinessRole.SUBSYSTEM,
    BusinessRole.QUALITY,
)

#: 数据里允许出现的全部角色
ALL_ROLES: tuple[BusinessRole, ...] = BUSINESS_ROLES + (BusinessRole.ADMIN,)

ROLE_VALUES: frozenset[str] = frozenset(role.value for role in ALL_ROLES)


# ── 工单状态 ───────────────────────────────────────────────


class TicketState(StrEnum):
    PENDING_APPROVAL = "pending_approval"
    #: 专项小组一步完成「确认问题 + 选择分系统并流转」
    PENDING_ROUTING = "pending_routing"
    PLANNING = "planning"
    PENDING_PLAN_CONFIRMATION = "pending_plan_confirmation"
    PROCESSING = "processing"
    PENDING_QUALITY_REVIEW = "pending_quality_review"
    #: 质量评审通过后由批准人复核，批准即闭环
    PENDING_FINAL_APPROVAL = "pending_final_approval"
    CLOSED = "closed"
    RETURNED = "returned"
    CANCELLED = "cancelled"


#: 正向主流程顺序（不含 returned / cancelled）
MAIN_FLOW_STATES: tuple[TicketState, ...] = (
    TicketState.PENDING_APPROVAL,
    TicketState.PENDING_ROUTING,
    TicketState.PLANNING,
    TicketState.PENDING_PLAN_CONFIRMATION,
    TicketState.PROCESSING,
    TicketState.PENDING_QUALITY_REVIEW,
    TicketState.PENDING_FINAL_APPROVAL,
    TicketState.CLOSED,
)

STATE_ORDER: tuple[TicketState, ...] = MAIN_FLOW_STATES + (
    TicketState.RETURNED,
    TicketState.CANCELLED,
)

STATE_VALUES: frozenset[str] = frozenset(state.value for state in STATE_ORDER)

TERMINAL_STATES: frozenset[TicketState] = frozenset(
    {TicketState.CLOSED, TicketState.CANCELLED}
)

#: 状态展示名称（契约 §3 表格同源）
STATE_LABELS: dict[TicketState, str] = {
    TicketState.PENDING_APPROVAL: "待审批",
    TicketState.PENDING_ROUTING: "待确认流转",
    TicketState.PLANNING: "闭环计划制定中",
    TicketState.PENDING_PLAN_CONFIRMATION: "待计划确认",
    TicketState.PROCESSING: "分析验证中",
    TicketState.PENDING_QUALITY_REVIEW: "待质量评审",
    TicketState.PENDING_FINAL_APPROVAL: "待批准人复核",
    TicketState.CLOSED: "已闭环",
    TicketState.RETURNED: "已退回",
    TicketState.CANCELLED: "已撤销",
}

#: 已闭环/已撤销之外的状态集合，用于“未闭环”查询与逾期判断
OPEN_STATES: frozenset[TicketState] = frozenset(STATE_ORDER) - TERMINAL_STATES

#: 专项小组数据范围：**批准人批准之后**的未闭环节点。
#: `pending_approval` 阶段问题归售前与批准人，专项小组不参与，不可见。
#: `returned` 额外按退回目标判断，见 taskforce_visible()。
TASKFORCE_VISIBLE_STATES: frozenset[TicketState] = (
    frozenset(OPEN_STATES) - {TicketState.PENDING_APPROVAL}
)

TASKFORCE_VISIBLE_VALUES: frozenset[str] = frozenset(
    state.value for state in TASKFORCE_VISIBLE_STATES
)


# ── 优先级 ─────────────────────────────────────────────────


class Priority(StrEnum):
    P0_BLOCKER = "p0_blocker"
    P1_CRITICAL = "p1_critical"
    P2_NORMAL = "p2_normal"
    P3_LOW = "p3_low"


DEFAULT_PRIORITY = Priority.P2_NORMAL
PRIORITY_VALUES: frozenset[str] = frozenset(p.value for p in Priority)


# ── 验证状态 ───────────────────────────────────────────────


class VerificationStatus(StrEnum):
    RESOLVED = "resolved"
    TEMPORARILY_RESOLVED = "temporarily_resolved"
    PENDING_REPRODUCTION = "pending_reproduction"
    UNRESOLVED = "unresolved"


VERIFICATION_STATUS_VALUES: frozenset[str] = frozenset(
    v.value for v in VerificationStatus
)


# ── 字段分组（PATCH / 动作 payload 共用）───────────────────

#: 创建阶段可编辑字段（PATCH 与退回后重新提交共用）
CREATION_FIELDS: tuple[str, ...] = (
    "title",
    "proposer",
    "proposer_department",
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

#: 退回售前重新提交时仍必须非空的业务必填字段（approver_id 不允许改）
CREATE_REQUIRED_BUSINESS_FIELDS: tuple[str, ...] = (
    "title",
    "proposer",
    "proposer_department",
    "product_line",
    "customer_name",
    "priority",
    "problem_type",
    "closure_requirement",
    "occurred_at",
    "location",
    "device_info",
    "description",
)


# ── 动作 ───────────────────────────────────────────────────


class TicketAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    #: 专项小组：确认问题描述 + 选定分系统与分系统负责人，一步流转到分系统
    ROUTE = "route"
    SUBMIT_PLAN = "submit_plan"
    CONFIRM_PLAN = "confirm_plan"
    SUBMIT_ANALYSIS = "submit_analysis"
    PASS_REVIEW = "pass_review"
    #: 批准人复核质量评审结果，批准即闭环
    APPROVE_CLOSURE = "approve_closure"
    RETURN = "return"
    RESUBMIT = "resubmit"
    CANCEL = "cancel"


ACTION_VALUES: frozenset[str] = frozenset(a.value for a in TicketAction)

#: 动作展示/序列化顺序（allowed_actions 按此排序）
ACTION_ORDER: tuple[TicketAction, ...] = (
    TicketAction.APPROVE,
    TicketAction.ROUTE,
    TicketAction.SUBMIT_PLAN,
    TicketAction.CONFIRM_PLAN,
    TicketAction.SUBMIT_ANALYSIS,
    TicketAction.PASS_REVIEW,
    TicketAction.APPROVE_CLOSURE,
    TicketAction.RESUBMIT,
    TicketAction.RETURN,
    TicketAction.REJECT,
    TicketAction.CANCEL,
)

#: 流程合并前的历史动作编码：不再产生，但历史日志仍按此展示
HISTORICAL_ACTIONS: dict[str, str] = {
    "confirm_problem": "确认问题（旧）",
    "accept": "确认接收（旧）",
    "register_defect": "登记缺陷并闭环（旧）",
}


# ── 动作权限/校验规则 ──────────────────────────────────────


class ActorScope(StrEnum):
    """动作执行人的范围要求（admin 兜底时跳过）。"""

    #: 只要角色匹配即可（专项小组、质量）
    ROLE = "role"
    #: 必须是工单指定的批准人
    ASSIGNED_APPROVER = "assigned_approver"
    #: 必须是创建人（售前）
    CREATOR = "creator"
    #: 必须是工单指定的分系统负责人
    SUBSYSTEM_OWNER = "subsystem_owner"
    #: 由 return_to_state 推导：退回 pending_approval 归创建人，
    #: 退回 planning/processing 归分系统负责人
    RETURN_TARGET = "return_target"


@dataclass(frozen=True)
class ActionRule:
    """单个 (当前状态, 动作) 的完整规则。"""

    target_state: TicketState | None
    roles: frozenset[BusinessRole]
    scope: ActorScope = ActorScope.ROLE
    #: payload 中必须能取到非空值的字段（也可能已存在工单上）
    required_fields: tuple[str, ...] = ()
    #: 必须填写意见
    comment_required: bool = False
    #: 允许写入 payload 的字段白名单（防止前端塞入未契约字段）
    payload_fields: tuple[str, ...] = ()
    #: return 动作允许的退回目标
    return_targets: frozenset[TicketState] = frozenset()
    #: 退回后固定写入的目标（reject 固定回 pending_approval）
    fixed_return_to: TicketState | None = None
    #: 该动作仅在工单处于 returned 且 return_to_state 命中此集合时可用
    #: （退回后由对应责任人一步完成修订与流转）
    only_when_return_target: frozenset[TicketState] = frozenset()


_R = ActionRule

#: (当前状态, 动作) -> 规则。所有状态流转必须命中此表。
ACTION_RULES: dict[tuple[TicketState, TicketAction], ActionRule] = {
    # 正向主流程
    (TicketState.PENDING_APPROVAL, TicketAction.APPROVE): _R(
        target_state=TicketState.PENDING_ROUTING,
        roles=frozenset({BusinessRole.APPROVER}),
        scope=ActorScope.ASSIGNED_APPROVER,
    ),
    # 专项小组一步到位：确认问题描述 + 选定分系统与负责人 → 直接进入分系统闭环计划
    (TicketState.PENDING_ROUTING, TicketAction.ROUTE): _R(
        target_state=TicketState.PLANNING,
        roles=frozenset({BusinessRole.TASKFORCE}),
        required_fields=("skill_group_id", "subsystem_owner_id"),
        payload_fields=("confirmation_comment", "skill_group_id", "subsystem_owner_id"),
    ),
    (TicketState.PLANNING, TicketAction.SUBMIT_PLAN): _R(
        target_state=TicketState.PENDING_PLAN_CONFIRMATION,
        roles=frozenset({BusinessRole.SUBSYSTEM}),
        scope=ActorScope.SUBSYSTEM_OWNER,
        required_fields=("long_term_measure", "planned_completion_at"),
        payload_fields=("temporary_measure", "long_term_measure", "planned_completion_at"),
    ),
    (TicketState.PENDING_PLAN_CONFIRMATION, TicketAction.CONFIRM_PLAN): _R(
        target_state=TicketState.PROCESSING,
        roles=frozenset({BusinessRole.PRESALES}),
        scope=ActorScope.CREATOR,
        payload_fields=("plan_confirmation_comment",),
    ),
    (TicketState.PROCESSING, TicketAction.SUBMIT_ANALYSIS): _R(
        target_state=TicketState.PENDING_QUALITY_REVIEW,
        roles=frozenset({BusinessRole.SUBSYSTEM}),
        scope=ActorScope.SUBSYSTEM_OWNER,
        required_fields=("initial_investigation", "root_cause", "analysis_report"),
        payload_fields=("initial_investigation", "root_cause", "analysis_report"),
    ),
    (TicketState.PENDING_QUALITY_REVIEW, TicketAction.PASS_REVIEW): _R(
        target_state=TicketState.PENDING_FINAL_APPROVAL,
        roles=frozenset({BusinessRole.QUALITY}),
        required_fields=(
            "verification_status",
            "verification_conclusion",
            "quality_review_result",
        ),
        payload_fields=(
            "verification_status",
            "verification_conclusion",
            "quality_review_result",
        ),
    ),
    # 批准人复核：批准即闭环
    (TicketState.PENDING_FINAL_APPROVAL, TicketAction.APPROVE_CLOSURE): _R(
        target_state=TicketState.CLOSED,
        roles=frozenset({BusinessRole.APPROVER}),
        scope=ActorScope.ASSIGNED_APPROVER,
    ),
    # 否决：批准人驳回
    (TicketState.PENDING_APPROVAL, TicketAction.REJECT): _R(
        target_state=TicketState.RETURNED,
        roles=frozenset({BusinessRole.APPROVER}),
        scope=ActorScope.ASSIGNED_APPROVER,
        comment_required=True,
        fixed_return_to=TicketState.PENDING_APPROVAL,
    ),
    # 三条退回路径
    (TicketState.PENDING_ROUTING, TicketAction.RETURN): _R(
        target_state=TicketState.RETURNED,
        roles=frozenset({BusinessRole.TASKFORCE}),
        comment_required=True,
        payload_fields=("return_to_state",),
        return_targets=frozenset({TicketState.PENDING_APPROVAL}),
    ),
    (TicketState.PENDING_PLAN_CONFIRMATION, TicketAction.RETURN): _R(
        target_state=TicketState.RETURNED,
        roles=frozenset({BusinessRole.PRESALES}),
        scope=ActorScope.CREATOR,
        comment_required=True,
        payload_fields=("return_to_state",),
        return_targets=frozenset({TicketState.PLANNING}),
    ),
    (TicketState.PENDING_QUALITY_REVIEW, TicketAction.RETURN): _R(
        target_state=TicketState.RETURNED,
        roles=frozenset({BusinessRole.QUALITY}),
        comment_required=True,
        payload_fields=("return_to_state",),
        return_targets=frozenset({TicketState.PROCESSING}),
    ),
    # 批准人复核驳回：退回质量重新评审
    (TicketState.PENDING_FINAL_APPROVAL, TicketAction.RETURN): _R(
        target_state=TicketState.RETURNED,
        roles=frozenset({BusinessRole.APPROVER}),
        scope=ActorScope.ASSIGNED_APPROVER,
        comment_required=True,
        payload_fields=("return_to_state",),
        return_targets=frozenset({TicketState.PENDING_QUALITY_REVIEW}),
    ),
    # 退回后处置：对应责任人在退回节点上一步完成「修订 + 流转」
    # 退回到售前（创建阶段）时售前携带创建字段重新提交，回到待审批
    (TicketState.RETURNED, TicketAction.RESUBMIT): _R(
        target_state=TicketState.PENDING_APPROVAL,
        roles=frozenset({BusinessRole.PRESALES}),
        scope=ActorScope.RETURN_TARGET,
        required_fields=CREATE_REQUIRED_BUSINESS_FIELDS,
        payload_fields=CREATION_FIELDS,
        only_when_return_target=frozenset({TicketState.PENDING_APPROVAL}),
    ),
    # 退回到闭环计划：分系统负责人直接修订并提交闭环计划
    (TicketState.RETURNED, TicketAction.SUBMIT_PLAN): _R(
        target_state=TicketState.PENDING_PLAN_CONFIRMATION,
        roles=frozenset({BusinessRole.SUBSYSTEM}),
        scope=ActorScope.RETURN_TARGET,
        required_fields=("long_term_measure", "planned_completion_at"),
        payload_fields=("temporary_measure", "long_term_measure", "planned_completion_at"),
        only_when_return_target=frozenset({TicketState.PLANNING}),
    ),
    # 退回到分析验证：分系统负责人直接修订并提交分析验证
    (TicketState.RETURNED, TicketAction.SUBMIT_ANALYSIS): _R(
        target_state=TicketState.PENDING_QUALITY_REVIEW,
        roles=frozenset({BusinessRole.SUBSYSTEM}),
        scope=ActorScope.RETURN_TARGET,
        required_fields=("initial_investigation", "root_cause", "analysis_report"),
        payload_fields=("initial_investigation", "root_cause", "analysis_report"),
        only_when_return_target=frozenset({TicketState.PROCESSING}),
    ),
    # 退回到质量评审：质量直接修订评审结论并重新提交
    (TicketState.RETURNED, TicketAction.PASS_REVIEW): _R(
        target_state=TicketState.PENDING_FINAL_APPROVAL,
        roles=frozenset({BusinessRole.QUALITY}),
        scope=ActorScope.RETURN_TARGET,
        required_fields=(
            "verification_status",
            "verification_conclusion",
            "quality_review_result",
        ),
        payload_fields=(
            "verification_status",
            "verification_conclusion",
            "quality_review_result",
        ),
        only_when_return_target=frozenset({TicketState.PENDING_QUALITY_REVIEW}),
    ),
    # 撤销
    (TicketState.PENDING_APPROVAL, TicketAction.CANCEL): _R(
        target_state=TicketState.CANCELLED,
        roles=frozenset({BusinessRole.PRESALES}),
        scope=ActorScope.CREATOR,
        comment_required=True,
    ),
    (TicketState.RETURNED, TicketAction.CANCEL): _R(
        target_state=TicketState.CANCELLED,
        roles=frozenset({BusinessRole.PRESALES}),
        scope=ActorScope.CREATOR,
        comment_required=True,
    ),
}

#: 状态 -> 允许的目标状态（admin 兜底撤销不计入，撤销目标为 cancelled）
TRANSITIONS: dict[TicketState, frozenset[TicketState]] = {}
for _state in STATE_ORDER:
    _targets: set[TicketState] = set()
    for (_frm, _act), _rule in ACTION_RULES.items():
        if _frm is _state and _rule.target_state is not None:
            _targets.add(_rule.target_state)
    # returned 的退回目标由各自责任的处置动作覆盖（见上方 returned 规则）
    TRANSITIONS[_state] = frozenset(_targets)

#: 动作 -> 业务必填字段（供文档/测试遍历）
ACTION_REQUIREMENTS: dict[TicketAction, tuple[str, ...]] = {
    action: rule.required_fields
    for (_state, action), rule in ACTION_RULES.items()
    if rule.required_fields
}

#: 退回目标 -> 重新提交后的责任角色与责任字段
RETURN_TARGET_RESPONSIBLE_ROLE: dict[TicketState, BusinessRole] = {
    TicketState.PENDING_APPROVAL: BusinessRole.PRESALES,
    TicketState.PENDING_QUALITY_REVIEW: BusinessRole.QUALITY,
    TicketState.PLANNING: BusinessRole.SUBSYSTEM,
    TicketState.PROCESSING: BusinessRole.SUBSYSTEM,
}


# ── 状态 -> 当前责任角色 ───────────────────────────────────


RESPONSIBLE_ROLE_BY_STATE: dict[TicketState, BusinessRole | None] = {
    TicketState.PENDING_APPROVAL: BusinessRole.APPROVER,
    TicketState.PENDING_ROUTING: BusinessRole.TASKFORCE,
    TicketState.PLANNING: BusinessRole.SUBSYSTEM,
    TicketState.PENDING_PLAN_CONFIRMATION: BusinessRole.PRESALES,
    TicketState.PROCESSING: BusinessRole.SUBSYSTEM,
    TicketState.PENDING_QUALITY_REVIEW: BusinessRole.QUALITY,
    TicketState.PENDING_FINAL_APPROVAL: BusinessRole.APPROVER,
    TicketState.CLOSED: None,
    TicketState.CANCELLED: None,
    TicketState.RETURNED: None,  # 由 return_to_state 决定
}

#: 责任角色落到的具体人员字段
RESPONSIBLE_USER_FIELD_BY_STATE: dict[TicketState, str | None] = {
    TicketState.PENDING_APPROVAL: "approver_id",
    TicketState.PENDING_FINAL_APPROVAL: "approver_id",
    TicketState.PLANNING: "subsystem_owner_id",
    TicketState.PENDING_PLAN_CONFIRMATION: "creator_id",
    TicketState.PROCESSING: "subsystem_owner_id",
}


def state_label(state: TicketState | str | None) -> str:
    """状态展示名称；未知/空值原样返回。"""
    if state is None:
        return ""
    try:
        return STATE_LABELS[_as_state(state)]
    except ValueError:
        return str(state)


def is_terminal(state: TicketState | str) -> bool:
    state = _as_state(state)
    return state in TERMINAL_STATES


def taskforce_visible(
    state: TicketState | str, return_to_state: TicketState | str | None = None
) -> bool:
    """专项小组能否看到该问题（数据范围）。

    规则：批准人批准之后的未闭环节点可见；待审批、已闭环、已撤销不可见。
    `returned` 按退回目标判断——退回目标是 `pending_approval` 时问题仍在审批前
    阶段（售前修改后重新提交审批），专项小组不可见。
    """
    state = _as_state(state)
    if state not in TASKFORCE_VISIBLE_STATES:
        return False
    if state is TicketState.RETURNED and return_to_state is not None:
        return _as_state(return_to_state) is not TicketState.PENDING_APPROVAL
    return True


def _as_state(state: TicketState | str) -> TicketState:
    return state if isinstance(state, TicketState) else TicketState(state)


def _as_action(action: TicketAction | str) -> TicketAction:
    return action if isinstance(action, TicketAction) else TicketAction(action)


def action_rule(
    state: TicketState | str, action: TicketAction | str
) -> ActionRule | None:
    """取 (状态, 动作) 的规则；不合法返回 None（调用方转 400）。"""
    try:
        return ACTION_RULES.get((_as_state(state), _as_action(action)))
    except ValueError:
        return None


def actions_for_state(state: TicketState | str) -> tuple[TicketAction, ...]:
    """某状态下契约允许的全部动作（仅按状态过滤，不含角色判断）。

    管理员兜底撤销（任意非终态）不在此表内，由服务层单独放开。
    """
    state = _as_state(state)
    return tuple(
        action for action in ACTION_ORDER if (state, action) in ACTION_RULES
    )


def target_state_for(
    state: TicketState | str,
    action: TicketAction | str,
    return_to_state: TicketState | str | None = None,
) -> TicketState:
    """计算动作完成后的目标状态。resubmit 由 return_to_state 决定。"""
    state = _as_state(state)
    action = _as_action(action)
    rule = ACTION_RULES.get((state, action))
    if rule is None:
        raise KeyError(f"{state}/{action} 不是合法动作")
    if rule.target_state is not None:
        return rule.target_state
    if return_to_state is None:
        raise ValueError("该动作需要 return_to_state 才能确定目标状态")
    return _as_state(return_to_state)


def responsible_role_for(
    state: TicketState | str, return_to_state: TicketState | str | None = None
) -> BusinessRole | None:
    """当前状态的责任角色；returned 由 return_to_state 推导。"""
    state = _as_state(state)
    if state is TicketState.RETURNED:
        if return_to_state is None:
            return None
        return RETURN_TARGET_RESPONSIBLE_ROLE.get(_as_state(return_to_state))
    return RESPONSIBLE_ROLE_BY_STATE.get(state)


def responsible_user_field_for(
    state: TicketState | str, return_to_state: TicketState | str | None = None
) -> str | None:
    """当前责任人员对应的工单字段名。"""
    state = _as_state(state)
    if state is TicketState.RETURNED:
        if return_to_state is None:
            return None
        target = _as_state(return_to_state)
        if target is TicketState.PENDING_APPROVAL:
            return "creator_id"
        if target in (TicketState.PLANNING, TicketState.PROCESSING):
            return "subsystem_owner_id"
        return None
    return RESPONSIBLE_USER_FIELD_BY_STATE.get(state)
