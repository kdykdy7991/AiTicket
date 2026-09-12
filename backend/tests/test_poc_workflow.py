"""POC 主流程端到端测试 + 领域状态机契约测试。"""

import pytest
from sqlalchemy import select

from app.domain.poc_workflow import (
    ACTION_REQUIREMENTS,
    ACTION_RULES,
    STATE_ORDER,
    TERMINAL_STATES,
    TicketAction,
    TicketState,
    actions_for_state,
    responsible_role_for,
)
from app.models.notification import DingtalkNotification
from app.models.ticket import Ticket
from helpers import MAIN_FLOW_STEPS, STATES_AFTER_STEPS, run_steps

EXPECTED_STATES = [TicketState.PENDING_APPROVAL] + STATES_AFTER_STEPS[1:]


def test_every_state_has_actions_and_terminals_are_final():
    """每个非终态至少有一个允许动作；终态没有任何动作。"""
    for state in STATE_ORDER:
        actions = actions_for_state(state)
        if state in TERMINAL_STATES:
            assert actions == (), f"终态 {state} 不应有动作"
        else:
            assert actions, f"非终态 {state} 没有任何允许动作"
        # 终态不应出现在任何规则的前置状态里
        if state in TERMINAL_STATES:
            assert not [k for k in ACTION_RULES if k[0] is state]


def test_responsible_role_mapping():
    assert responsible_role_for(TicketState.PENDING_APPROVAL) == "approver"
    assert responsible_role_for(TicketState.PENDING_CONFIRMATION) == "taskforce"
    assert responsible_role_for(TicketState.PENDING_ROUTING) == "taskforce"
    assert responsible_role_for(TicketState.PENDING_ACCEPTANCE) == "subsystem"
    assert responsible_role_for(TicketState.PLANNING) == "subsystem"
    assert responsible_role_for(TicketState.PENDING_PLAN_CONFIRMATION) == "presales"
    assert responsible_role_for(TicketState.PROCESSING) == "subsystem"
    assert responsible_role_for(TicketState.PENDING_QUALITY_REVIEW) == "quality"
    assert responsible_role_for(TicketState.PENDING_DEFECT_REGISTRATION) == "quality"
    assert responsible_role_for(TicketState.CLOSED) is None
    assert responsible_role_for(TicketState.RETURNED, TicketState.PLANNING) == "subsystem"
    assert responsible_role_for(TicketState.RETURNED, TicketState.PENDING_APPROVAL) == "presales"


def test_required_action_fields_match_contract():
    """必填项契约：与总约定第 3.1 节一致。"""
    assert ACTION_REQUIREMENTS[TicketAction.ROUTE] == ("skill_group_id", "subsystem_owner_id")
    assert ACTION_REQUIREMENTS[TicketAction.SUBMIT_PLAN] == (
        "long_term_measure",
        "planned_completion_at",
    )
    assert ACTION_REQUIREMENTS[TicketAction.SUBMIT_ANALYSIS] == (
        "initial_investigation",
        "root_cause",
        "analysis_report",
    )
    assert ACTION_REQUIREMENTS[TicketAction.PASS_REVIEW] == (
        "verification_status",
        "verification_conclusion",
        "quality_review_result",
    )
    assert ACTION_REQUIREMENTS[TicketAction.REGISTER_DEFECT] == (
        "defect_id",
        "defect_repository_path",
    )


async def test_create_formal_ticket_enters_pending_approval(api):
    api.as_("presales01")
    resp = await api.create_ticket()
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]

    assert data["state"] == "pending_approval"
    assert data["number"]
    assert data["is_draft"] is False
    assert data["priority"] == "p2_normal"
    assert data["approver_id"] == api.uid("approver01")
    assert data["creator_id"] == api.uid("presales01")
    assert data["creator_department"] == "默认组" or data["creator_department"] is None
    assert data["current_responsible_role"] == "approver"
    assert data["current_responsible_user_id"] == api.uid("approver01")
    # 创建人在待审批阶段只能撤销，审批动作属于被指定的批准人
    assert data["allowed_actions"] == ["cancel"]
    assert data["state_version"] == 1
    assert data["is_overdue"] is False
    assert [log["to_state"] for log in data["state_logs"]] == ["pending_approval"]

    api.as_("approver01")
    approver_view = await api.detail(data["id"])
    assert approver_view["allowed_actions"] == ["approve", "reject"]


async def test_full_main_flow_from_presales_to_closed(api):
    """售前提交 → 批准 → 确认 → 流转 → 接收 → 计划 → 确认 → 分析 → 评审 → 入库闭环。"""
    api.as_("presales01")
    created = await api.create_ticket()
    assert created.status_code == 201, created.text
    ticket_id = created.json()["data"]["id"]

    # 分系统在 route 时才确定，先取出两个 ID
    skill_group_id = api.sg("系统总体")
    subsystem_owner_id = api.uid("subsystem01")

    observed_states = [TicketState.PENDING_APPROVAL]
    for username, action, payload, comment in MAIN_FLOW_STEPS:
        api.as_(username)
        if action is TicketAction.ROUTE:
            payload = {
                "skill_group_id": skill_group_id,
                "subsystem_owner_id": subsystem_owner_id,
            }
        detail = await api.acted(ticket_id, action.value, payload=payload, comment=comment)
        observed_states.append(TicketState(detail["state"]))
    assert observed_states == EXPECTED_STATES

    api.as_("quality01")
    final = await api.detail(ticket_id)
    assert final["state"] == "closed"
    assert final["allowed_actions"] == []
    assert final["verification_status"] == "resolved"
    assert final["defect_id"] == "BUG-2026-0912"
    assert final["defect_repository_path"].startswith("svn://")
    assert final["defect_registered_at"] is not None
    assert final["defect_registered_by_id"] == api.uid("quality01")
    assert final["closed_at"] is not None
    assert final["actual_completion_at"] is not None
    assert final["is_overdue"] is False
    # 建单日志 1 条 + 9 个动作
    assert final["state_version"] == 10
    assert len(final["state_logs"]) == 10

    actions = [log["action"] for log in final["state_logs"]]
    assert actions[0] is None
    assert actions[1:] == [step[1].value for step in MAIN_FLOW_STEPS]

    approve_log = final["state_logs"][1]
    assert approve_log["operator_name"] == "邱总"
    assert approve_log["operator_role"] == "approver"
    assert approve_log["comment"] == "同意，转专项小组确认"
    assert approve_log["from_state"] == "pending_approval"
    assert approve_log["to_state"] == "pending_confirmation"
    assert approve_log["responsible_role_snapshot"] == "taskforce"
    assert approve_log["state_version"] == 2

    route_log = next(log for log in final["state_logs"] if log["action"] == "route")
    assert route_log["payload"]["skill_group_id"] == skill_group_id
    assert route_log["responsible_role_snapshot"] == "subsystem"
    assert route_log["responsible_user_id_snapshot"] == subsystem_owner_id

    plan_log = next(log for log in final["state_logs"] if log["action"] == "submit_plan")
    assert plan_log["payload"]["long_term_measure"].startswith("升级终端固件")


async def test_state_logs_endpoint_matches_detail(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    api.as_("approver01")
    await api.action(ticket_id, "approve", comment="同意")

    resp = await api.c.get(f"/api/v1/tickets/{ticket_id}/state-logs")
    assert resp.status_code == 200, resp.text
    logs = resp.json()["data"]
    assert [log["to_state"] for log in logs] == ["pending_approval", "pending_confirmation"]
    assert logs[-1]["operator_role"] == "approver"


async def test_patch_cannot_change_state_or_responsible_people(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]

    for forbidden in (
        {"state": "closed"},
        {"skill_group_id": api.sg("系统总体")},
        {"subsystem_owner_id": api.uid("subsystem01")},
        {"approver_id": api.uid("approver02")},
    ):
        resp = await api.c.patch(f"/api/v1/tickets/{ticket_id}", json=forbidden)
        assert resp.status_code == 422, resp.text

    # 允许创建人在待审批阶段修改创建阶段字段
    ok = await api.c.patch(f"/api/v1/tickets/{ticket_id}", json={"title": "修改后的问题名称"})
    assert ok.status_code == 200, ok.text
    assert ok.json()["title"] == "修改后的问题名称"
    assert ok.json()["state"] == "pending_approval"


async def test_patch_rejected_for_non_owner(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]

    api.as_("approver01")
    resp = await api.c.patch(f"/api/v1/tickets/{ticket_id}", json={"title": "越权修改"})
    assert resp.status_code == 403, resp.text


async def test_overdue_flag_follows_planned_completion(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    api.as_("approver01")
    await api.action(ticket_id, "approve")
    api.as_("taskforce01")
    await api.action(ticket_id, "confirm_problem")
    await api.action(
        ticket_id,
        "route",
        payload={
            "skill_group_id": api.sg("终端系统"),
            "subsystem_owner_id": api.uid("subsystem03"),
        },
    )
    api.as_("subsystem03")
    await api.action(ticket_id, "accept")
    detail = await api.acted(
        ticket_id,
        "submit_plan",
        payload={
            "long_term_measure": "修复固件",
            "planned_completion_at": "2020-01-01T00:00:00+00:00",
        },
    )
    assert detail["is_overdue"] is True

    # 列表按逾期过滤
    resp = await api.c.get("/api/v1/tickets", params={"is_overdue": "true"})
    assert resp.status_code == 200
    assert [t["id"] for t in resp.json()["data"]] == [ticket_id]


async def test_notification_failure_does_not_rollback_action(api):
    """分系统未配置钉钉机器人时，动作依然成功，并留下失败记录。"""
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    api.as_("approver01")
    detail = await api.acted(ticket_id, "approve")
    assert detail["state"] == "pending_confirmation"

    async with api.session() as s:
        rows = (
            await s.execute(
                select(DingtalkNotification).where(DingtalkNotification.ticket_id == ticket_id)
            )
        ).scalars().all()
        assert rows, "通知失败也必须留记录"
        assert rows[-1].type == "poc_approve"
        assert rows[-1].success is False
        assert rows[-1].target_user_id is None  # 专项小组是角色级责任，无具体人员

        ticket = (await s.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one()
        assert ticket.state == "pending_confirmation"
        assert ticket.state_version == 2


async def test_draft_flow_submits_into_pending_approval(api):
    api.as_("presales01")
    draft = await api.create_ticket(draft=True)
    assert draft.status_code == 201, draft.text
    draft_data = draft.json()["data"]
    draft_id = draft_data["id"]
    assert draft_data["is_draft"] is True
    assert draft_data["number"] is None
    assert draft_data["allowed_actions"] == []

    drafts = await api.c.get("/api/v1/tickets/drafts")
    assert [d["id"] for d in drafts.json()["data"]] == [draft_id]

    # 草稿不进入正式列表
    listed = await api.c.get("/api/v1/tickets")
    assert listed.json()["data"] == []

    submit = await api.c.post(f"/api/v1/tickets/drafts/{draft_id}/submit")
    assert submit.status_code == 200, submit.text
    data = submit.json()["data"]
    assert data["state"] == "pending_approval"
    assert data["is_draft"] is False
    assert data["number"]

    listed = await api.c.get("/api/v1/tickets")
    assert [t["id"] for t in listed.json()["data"]] == [draft_id]


async def test_draft_submit_requires_approver(api):
    api.as_("presales01")
    draft_id = (await api.create_ticket(draft=True, approver_id=None)).json()["data"]["id"]
    resp = await api.c.post(f"/api/v1/tickets/drafts/{draft_id}/submit")
    assert resp.status_code == 400, resp.text
    assert "approver_id" in resp.text


@pytest.mark.parametrize("index", range(len(MAIN_FLOW_STEPS) - 1))
async def test_illegal_state_jump_returns_400(api, index):
    """当前节点责任人执行后续节点动作 → 400（非法跳状态）。"""
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, index)

    actor, _action, _payload, _comment = MAIN_FLOW_STEPS[index]
    later_action = MAIN_FLOW_STEPS[index + 1][1]
    api.as_(actor)
    resp = await api.action(ticket_id, later_action.value, expect=400)
    assert "不支持动作" in resp.text
