"""Ticket state machine — 7 状态，按新流程定义流转规则与操作权限。

状态：
  pending    待受理（初始）
  open       处理中
  resolved   已处理
  on_hold    暂缓处理
  archived   已归档（终态）
  returned   已退回
  cancelled  已撤销（终态）

操作权限：
  分派(pending→open)                                → 部门对接人
  已处理(open→resolved)、暂缓(open→on_hold)          → 处理人
  确认(on_hold→resolved)                            → 处理人
  归档(resolved→archived)                            → 客服团队
  退回(pending/open/on_hold/resolved→上一状态)       → 对应处理人
"""

from app.core.exceptions import StateTransitionError

# 8 状态流转规则：{from_state: [to_state, ...]}
TRANSITIONS: dict[str, list[str]] = {
    "pending": ["open", "cancelled", "returned"],
    "open": ["resolved", "on_hold", "pending", "cancelled"],
    "on_hold": ["resolved", "open", "cancelled"],
    "resolved": ["archived", "open", "on_hold"],
    "returned": ["pending", "cancelled"],
    # 终态
    "archived": [],
    "cancelled": [],
}

# 需要填原因的目标状态：退回 / 暂缓 / 撤销
# 非 pending 状态退回时目标为「上一状态」；pending 退回时目标为 returned
STATES_REQUIRE_REASON_FROM: dict[str, set[str]] = {
    "pending": {"open", "on_hold", "resolved"},  # 处理中/暂缓/已处理 退回至待受理需原因
    "open": {"on_hold", "resolved"},             # 暂缓/已处理 退回至处理中需原因
    "on_hold": {"open", "resolved"},             # 处理中→暂缓 / 已处理→暂缓 都需原因
    "returned": {"pending"},                      # 待受理→已退回需原因
    "cancelled": {"pending", "open", "on_hold", "returned"},  # 撤销需原因
}

# 终态（不可再流转）
TERMINAL_STATES = {"archived", "cancelled"}


def validate_transition(from_state: str, to_state: str) -> None:
    """校验状态流转是否合法，非法则抛 StateTransitionError。"""
    if from_state in TERMINAL_STATES:
        raise StateTransitionError(from_state, to_state)
    allowed = TRANSITIONS.get(from_state, [])
    if to_state not in allowed:
        raise StateTransitionError(from_state, to_state)


def requires_reason(from_state: str, to_state: str) -> bool:
    """该流转是否需要填写原因。"""
    return to_state in STATES_REQUIRE_REASON_FROM and from_state in STATES_REQUIRE_REASON_FROM[to_state]
