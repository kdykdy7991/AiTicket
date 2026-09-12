"""角色权限与人员范围测试。"""

import pytest

from app.domain.poc_workflow import TicketAction, TicketState
from helpers import MAIN_FLOW_STEPS, STATES_AFTER_STEPS, run_steps

#: 不应具备主流程动作权限的业务账号（admin 拥有兜底权限，不在其中）
WRONG_ACTORS = [
    "presales02",
    "approver02",
    "taskforce01",
    "subsystem02",
    "subsystem06",
    "quality01",
]


def _payload_for(api, step_payload: dict, action: TicketAction) -> dict:
    if action is TicketAction.ROUTE:
        return {
            "skill_group_id": api.sg("系统总体"),
            "subsystem_owner_id": api.uid("subsystem01"),
        }
    return step_payload


@pytest.mark.parametrize("index", range(len(MAIN_FLOW_STEPS)))
async def test_only_current_node_actor_is_allowed(api, index):
    """每个动作只有规定角色+指定人员可执行，其他业务角色一律 403。"""
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, index)

    actor, action, payload, comment = MAIN_FLOW_STEPS[index]
    payload = _payload_for(api, payload, action)

    api.as_(actor)
    version = (await api.detail(ticket_id))["state_version"]

    for wrong in WRONG_ACTORS:
        if wrong == actor:
            continue
        api.as_(wrong)
        await api.action(
            ticket_id,
            action.value,
            payload=payload,
            comment=comment or "越权尝试",
            version=version,
            expect=403,
        )

    # 正确的人仍然可以执行
    api.as_(actor)
    detail = await api.acted(
        ticket_id, action.value, payload=payload, comment=comment, version=version
    )
    assert detail["state"] == STATES_AFTER_STEPS[index + 1].value


async def test_same_subsystem_member_can_view_but_not_act(api):
    """同分系统其他成员可以查看，但不能执行分系统动作。"""
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 3)  # pending_acceptance

    api.as_("subsystem06")
    detail = await api.detail(ticket_id)
    assert detail["state"] == "pending_acceptance"
    assert "accept" not in detail["allowed_actions"]

    await api.action(ticket_id, "accept", expect=403)


async def test_admin_has_fallback_power(api):
    """管理员可代操作，但不在业务人员列表中展示。"""
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]

    api.as_("admin")
    detail = await api.detail(ticket_id)
    assert "approve" in detail["allowed_actions"]
    assert detail["state"] == "pending_approval"

    updated = await api.acted(ticket_id, "approve", comment="管理员代审批")
    assert updated["state"] == "pending_confirmation"
    assert updated["state_logs"][-1]["operator_name"] == "系统管理员"

    admin_view = (await api.c.get("/api/v1/users", params={"role": "approver"})).json()["data"]
    assert admin_view and all("approver" in u["roles"] for u in admin_view)

    api.as_("presales01")
    users = (await api.c.get("/api/v1/users")).json()["data"]
    assert users and all("admin" not in u["roles"] for u in users)

    roles = (await api.c.get("/api/v1/meta/poc-workflow")).json()["data"]
    assert "admin" not in roles["selectable_roles"]
    assert "admin" in roles["business_roles"]


async def test_presales_only_sees_own_tickets(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]

    api.as_("presales02")
    listed = await api.c.get("/api/v1/tickets")
    assert listed.json()["data"] == []
    await api.detail(ticket_id, expect=403)
    await api.action(ticket_id, "cancel", comment="越权撤销", expect=403)

    export = await api.c.get("/api/v1/tickets/export")
    assert export.status_code == 200
    assert "POC 现场终端掉线" not in export.text


async def test_approver_scope_is_limited_to_assigned_tickets(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]

    api.as_("approver02")
    assert (await api.c.get("/api/v1/tickets")).json()["data"] == []
    await api.detail(ticket_id, expect=403)
    await api.action(ticket_id, "approve", expect=403)

    api.as_("approver01")
    listed = await api.c.get("/api/v1/tickets")
    assert [t["id"] for t in listed.json()["data"]] == [ticket_id]


async def test_subsystem_scope_follows_skill_group(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 3)  # 流转到系统总体

    api.as_("subsystem02")  # 卫星平台
    assert (await api.c.get("/api/v1/tickets")).json()["data"] == []
    await api.detail(ticket_id, expect=403)

    api.as_("subsystem01")
    assert [t["id"] for t in (await api.c.get("/api/v1/tickets")).json()["data"]] == [ticket_id]


async def test_taskforce_sees_only_unclosed_tickets(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, len(MAIN_FLOW_STEPS))  # 闭环

    api.as_("taskforce01")
    assert (await api.c.get("/api/v1/tickets")).json()["data"] == []
    await api.detail(ticket_id, expect=403)


async def test_quality_sees_every_ticket(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]

    api.as_("quality01")
    assert [t["id"] for t in (await api.c.get("/api/v1/tickets")).json()["data"]] == [ticket_id]
    assert (await api.detail(ticket_id))["state"] == "pending_approval"


async def test_export_respects_scope(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    number = (await api.detail(ticket_id))["number"]

    api.as_("approver02")
    export = await api.c.get("/api/v1/tickets/export")
    assert export.status_code == 200
    assert number not in export.text

    api.as_("approver01")
    export = await api.c.get("/api/v1/tickets/export")
    assert number in export.text
    assert "问题编号" in export.text
    assert "SVN路径" in export.text


async def test_legacy_ticket_and_draft_are_hidden_from_lists(api):
    """非 POC 历史数据与草稿都不出现在正式列表。"""
    from app.models.ticket import Ticket

    async with api.session() as s:
        legacy = Ticket(
            number="20250101-0001",
            state=TicketState.CANCELLED.value,
            priority="p2_normal",
            description="旧客服工单",
            creator_id=api.uid("presales01"),
            legacy_state=TicketState.CANCELLED.value,
            state_version=1,
        )
        s.add(legacy)
        await s.commit()
        legacy_id = legacy.id

    api.as_("quality01")
    assert (await api.c.get("/api/v1/tickets")).json()["data"] == []
    await api.detail(legacy_id, expect=404)
