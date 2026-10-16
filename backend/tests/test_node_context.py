"""Read-only Node Context follows the existing category, chain and state facts."""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.ticket import Ticket
from app.models.user import User
from test_refine import renv, set_existing_open_ticket  # noqa: F401
from test_transfer import tenv  # noqa: F401
from test_workflow_regression import as_user


async def _detail(env, ticket_id):
    response = await env["client"].get(f"/api/v1/tickets/{ticket_id}")
    assert response.status_code == 200, response.text
    return response.json()


async def test_assurance_triage_and_hardware_processing_same_department(renv):
    ticket = await renv["create_ticket"]()
    first = await _detail(renv, ticket["id"])
    assert first["node_context"]["node_type"] == "triage"
    assert first["node_context"]["department_code"] == "售后"
    assert "refine" in {a["action"] for a in first["node_context"]["allowed_actions"]}

    refined = await renv["refine"](ticket["id"], 2322)
    assert refined["node_context"]["node_type"] == "processing"
    assert refined["node_context"]["department_code"] == "售后"
    assert refined["node_context"]["dispatch_step_index"] == 1
    dispatched = await renv["patch"](
        ticket["id"], {"state": "open", "owner_id": renv["aftersale_user"]}
    )
    assert dispatched["state"] == "open"


async def test_triage_rejects_direct_dispatch_and_reply_even_for_admin(renv):
    ticket = await renv["create_ticket"]()
    direct_dispatch = await renv["client"].patch(
        f"/api/v1/tickets/{ticket['id']}",
        json={"state": "open", "owner_id": renv["aftersale_user"]},
    )
    assert direct_dispatch.status_code == 403
    # Model an older open ticket at a judgement node: admin still cannot
    # bypass refinement with a direct resolve or ordinary reply.
    await set_existing_open_ticket(renv, ticket["id"])
    direct_resolve = await renv["client"].patch(
        f"/api/v1/tickets/{ticket['id']}", json={"state": "resolved"}
    )
    assert direct_resolve.status_code == 422
    reply = await renv["client"].post(
        f"/api/v1/tickets/{ticket['id']}/articles",
        data={"type": "reply", "body": "跳过分诊"},
    )
    assert reply.status_code == 422
    detail = await _detail(renv, ticket["id"])
    assert detail["can_reply"] is False
    assert "reply" not in {a["action"] for a in detail["node_context"]["allowed_actions"]}


async def test_refine_to_other_department_and_return_recompute_node(renv):
    ticket = await renv["create_ticket"]()
    refined = await renv["refine"](ticket["id"], 2302)
    assert refined["node_context"]["node_type"] == "processing"
    assert refined["node_context"]["department_code"] == "平台运维组"

    await renv["patch"](ticket["id"], {"state": "returned", "reason": "重新判断"})
    restored = await _detail(renv, ticket["id"])
    assert restored["node_context"]["node_type"] == "triage"
    assert restored["node_context"]["category_id"] == 2301
    assert restored["node_context"]["department_code"] == "售后"


async def test_phone_feedback_takes_precedence_over_processing(tenv):
    ticket = await tenv["create_ticket"](category_id=2298)
    initial = await _detail(tenv, ticket["id"])
    assert initial["node_context"]["node_type"] == "processing"
    assert initial["node_context"]["department_code"] == "平台运维组"

    await tenv["patch"](ticket["id"], {"state": "open", "owner_id": tenv["platform_user"]})
    with as_user(tenv["platform_user"], "handler"):
        response = await tenv["client"].post(
            f"/api/v1/tickets/{ticket['id']}/articles",
            data={"type": "reply", "body": "处理完成"},
        )
    assert response.status_code == 201, response.text
    feedback = await _detail(tenv, ticket["id"])
    assert feedback["node_context"]["node_type"] == "phone_feedback"
    assert feedback["node_context"]["dispatch_stage"] == "phone_feedback"
    assert feedback["node_context"]["department_code"] == "售后"

    await tenv["patch"](ticket["id"], {"state": "open", "owner_id": tenv["aftersale_user"]})
    open_feedback = await _detail(tenv, ticket["id"])
    assert open_feedback["node_context"]["node_type"] == "phone_feedback"


async def test_same_department_without_feedback_stage_is_processing(tenv):
    ticket = await tenv["create_ticket"](category_id=2203)
    detail = await _detail(tenv, ticket["id"])
    assert detail["node_context"]["department_code"] == "售后"
    assert detail["node_context"]["node_type"] == "processing"


async def test_resolved_closure_and_reopen_restore_processing(tenv):
    ticket = await tenv["create_ticket"](category_id=2299)
    await tenv["patch"](ticket["id"], {"state": "open", "owner_id": tenv["platform_user"]})
    with as_user(tenv["platform_user"], "handler"):
        response = await tenv["client"].post(
            f"/api/v1/tickets/{ticket['id']}/articles",
            data={"type": "reply", "body": "处理完成"},
        )
    assert response.status_code == 201, response.text
    resolved = await _detail(tenv, ticket["id"])
    assert resolved["node_context"]["node_type"] == "closure"
    assert "archive" in {a["action"] for a in resolved["node_context"]["allowed_actions"]}

    await tenv["patch"](ticket["id"], {
        "is_callbacked": True, "satisfaction": "dissatisfied",
        "unsatisfied_reason": "仍未解决",
    })
    dissatisfied = await _detail(tenv, ticket["id"])
    assert dissatisfied["node_context"]["node_type"] == "closure"
    assert "archive" not in {a["action"] for a in dissatisfied["node_context"]["allowed_actions"]}

    await tenv["patch"](ticket["id"], {"state": "open", "reason": "需重新处理"})
    reopened = await _detail(tenv, ticket["id"])
    assert reopened["node_context"]["node_type"] == "processing"
    assert reopened["node_context"]["department_code"] == "平台运维组"


async def test_node_does_not_depend_on_viewer_but_actions_do(renv):
    ticket = await renv["create_ticket"]()
    outsider = await _detail(renv, ticket["id"])
    with as_user(999999, "agent"):
        other = await _detail(renv, ticket["id"])
    assert outsider["node_context"]["node_type"] == other["node_context"]["node_type"] == "triage"
    assert "refine" not in {a["action"] for a in other["node_context"]["allowed_actions"]}


async def test_constellation_triage_then_core_network_processing(renv):
    factory = async_sessionmaker(renv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        lead_group = SkillGroup(name="星座大系统负责人")
        dev_group = SkillGroup(name="软件开发组")
        lead = User(username="node-lead", name="星座负责人", password_hash="x", role="handler")
        dev = User(username="node-dev", name="开发处理人", password_hash="x", role="handler")
        db.add_all([lead_group, dev_group, lead, dev])
        await db.flush()
        db.add_all([
            UserSkillGroup(user_id=lead.id, skill_group_id=lead_group.id, is_dispatcher=True),
            UserSkillGroup(user_id=dev.id, skill_group_id=dev_group.id, is_dispatcher=True),
            DispatchChain(category_id=2310, steps=[{"order": 1, "department_code": "星座大系统负责人"}]),
            DispatchChain(category_id=2311, steps=[{"order": 1, "department_code": "软件开发组"}]),
        ])
        await db.commit()

    ticket = await renv["create_ticket"]()
    star = await renv["refine"](ticket["id"], 2310)
    assert star["node_context"]["node_type"] == "triage"
    assert star["node_context"]["department_code"] == "星座大系统负责人"
    with as_user(lead.id, "handler"):
        lead_view = await _detail(renv, ticket["id"])
        assert "refine" in {a["action"] for a in lead_view["node_context"]["allowed_actions"]}
        assert "dispatch" not in {a["action"] for a in lead_view["node_context"]["allowed_actions"]}
        core = await renv["refine"](ticket["id"], 2311)
    assert core["node_context"]["node_type"] == "processing"
    assert core["node_context"]["department_code"] == "软件开发组"
    with as_user(dev.id, "handler"):
        core_view = await _detail(renv, ticket["id"])
        assert "dispatch" in {a["action"] for a in core_view["node_context"]["allowed_actions"]}


async def test_invalid_chain_step_returns_explicit_conflict(tenv):
    ticket = await tenv["create_ticket"]()
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        persisted = await db.get(Ticket, ticket["id"])
        persisted.dispatch_step_index = 99
        await db.commit()
    response = await tenv["client"].get(f"/api/v1/tickets/{ticket['id']}")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "node_context_conflict"


async def test_admin_cannot_refine_outside_triage_node(renv):
    ticket = await renv["create_ticket"]()
    factory = async_sessionmaker(renv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        persisted = await db.get(Ticket, ticket["id"])
        persisted.dispatch_chain_steps = None  # legacy/manual ticket at a different department
        persisted.dispatch_step_index = None
        persisted.skill_group_id = renv["sg_platform"]
        await db.commit()
    detail = await _detail(renv, ticket["id"])
    assert detail["node_context"]["node_type"] == "processing"
    assert detail["can_refine"] is False
    response = await renv["client"].post(
        f"/api/v1/tickets/{ticket['id']}/refine", json={"category_id": 2302}
    )
    assert response.status_code == 403


async def test_returned_ticket_is_intake_and_terminal_ticket_has_no_active_node(tenv):
    ticket = await tenv["create_ticket"](category_id=2299)
    returned = await tenv["patch"](
        ticket["id"], {"state": "returned", "reason": "请创建人补充"}
    )
    assert returned["state"] == "returned"
    returned_detail = await _detail(tenv, ticket["id"])
    assert returned_detail["node_context"]["node_type"] == "intake"

    await tenv["patch"](ticket["id"], {"state": "cancelled", "reason": "撤销"})
    terminal = await _detail(tenv, ticket["id"])
    assert terminal["node_context"]["node_type"] is None
    assert terminal["node_context"]["allowed_actions"] == []
