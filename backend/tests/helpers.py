"""POC 流程测试辅助：主流程步骤与部分推进。"""

from app.domain.poc_workflow import TicketAction, TicketState

#: 主流程动作序列（不含建单）。route 的 payload 由 run_steps 动态填充。
MAIN_FLOW_STEPS = [
    ("approver01", TicketAction.APPROVE, {}, "同意，转专项小组确认并流转"),
    ("taskforce01", TicketAction.ROUTE, {}, "问题描述准确，流转分系统整改"),
    (
        "subsystem01",
        TicketAction.SUBMIT_PLAN,
        {
            "temporary_measure": "临时重启终端恢复业务",
            "initial_investigation": "初步定位为固件心跳超时",
            "long_term_measure": "升级终端固件并补充回归测试",
            "planned_completion_at": "2026-12-31T18:00:00+08:00",
        },
        None,
    ),
    ("presales01", TicketAction.CONFIRM_PLAN, {"plan_confirmation_comment": "计划可行"}, None),
    (
        "subsystem01",
        TicketAction.SUBMIT_ANALYSIS,
        {
            "root_cause": "固件 3.2.1 心跳重连逻辑缺陷",
            "analysis_report": "分析报告正文：复现三次，定位到重连定时器",
        },
        None,
    ),
    (
        "quality01",
        TicketAction.PASS_REVIEW,
        {
            "verification_status": "resolved",
            "verification_conclusion": "验证通过，问题已解决",
            "quality_review_result": "同意纳入缺陷库",
        },
        None,
    ),
    ("approver01", TicketAction.APPROVE_CLOSURE, {}, "评审结果确认，批准闭环"),
]

#: 执行完前 n 步后工单所处的状态
STATES_AFTER_STEPS = [
    TicketState.PENDING_APPROVAL,
    TicketState.PENDING_ROUTING,
    TicketState.PLANNING,
    TicketState.PENDING_PLAN_CONFIRMATION,
    TicketState.PROCESSING,
    TicketState.PENDING_QUALITY_REVIEW,
    TicketState.PENDING_FINAL_APPROVAL,
    TicketState.CLOSED,
]

#: 某个状态下允许执行的动作（第一个是主流程正向动作）
FORWARD_ACTION_BY_STATE = {
    TicketState.PENDING_APPROVAL: TicketAction.APPROVE,
    TicketState.PENDING_ROUTING: TicketAction.ROUTE,
    TicketState.PLANNING: TicketAction.SUBMIT_PLAN,
    TicketState.PENDING_PLAN_CONFIRMATION: TicketAction.CONFIRM_PLAN,
    TicketState.PROCESSING: TicketAction.SUBMIT_ANALYSIS,
    TicketState.PENDING_QUALITY_REVIEW: TicketAction.PASS_REVIEW,
    TicketState.PENDING_FINAL_APPROVAL: TicketAction.APPROVE_CLOSURE,
}


async def run_steps(api, ticket_id: int, count: int, start: int = 0) -> None:
    """在已建好的工单上执行主流程第 start..count-1 步。"""
    for username, action, payload, comment in MAIN_FLOW_STEPS[start:count]:
        api.as_(username)
        if action is TicketAction.ROUTE:
            payload = {
                "skill_group_id": api.sg("系统总体"),
                "subsystem_owner_id": api.uid("subsystem01"),
            }
        await api.action(ticket_id, action.value, payload=payload, comment=comment)


async def advance_to(api, ticket_id: int, state: TicketState) -> int:
    """推进到指定状态，返回已执行步数。"""
    steps = STATES_AFTER_STEPS.index(state)
    await run_steps(api, ticket_id, steps)
    return steps
