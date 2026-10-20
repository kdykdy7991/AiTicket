"""Second-level constellation triage keeps category as the only routing input."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.node_form import FormBinding, FormDefinition, TicketNodeSubmission
from app.models.ticket import Article, Ticket
from app.models.user import User
from scripts.seed_constellation_triage_form import seed_constellation_triage_form
from test_refine import async_sessionmaker_for, renv
from test_triage_form import install_form as install_after_sales_form, payload as triage_payload
from test_workflow_regression import as_user


TARGETS = ((2311, "核心网系统", "软件开发组"),
           (2312, "测运控系统", "测运控组"),
           (2313, "卫星系统", "整星产品"))


async def setup_triage(env):
    after_sales_id = await install_after_sales_form(env)
    factory = async_sessionmaker_for(env["engine"])
    async with factory() as db:
        (await db.get(TicketCategory, 2301)).requires_callback = True
        lead = (await db.execute(select(User).where(User.username == "triage-star-owner"))).scalar_one()
        users = {}
        for category_id, category_name, department in TARGETS:
            category = await db.get(TicketCategory, category_id)
            if category is None:
                category = TicketCategory(id=category_id, parent_id=2310, name=category_name,
                                          level=3, sort_order=category_id - 2310, is_active=True,
                                          created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
                db.add(category)
            group = SkillGroup(name=department)
            user = User(username=f"constellation-{category_id}", name=f"{department}处理人",
                        role="handler", password_hash="x")
            db.add_all([group, user])
            await db.flush()
            db.add(UserSkillGroup(user_id=user.id, skill_group_id=group.id, is_dispatcher=True))
            db.add(DispatchChain(category_id=category_id, steps=[
                {"order": 1, "department_code": department},
                {"order": 2, "department_code": "售后", "stage": "phone_feedback"},
            ]))
            users[category_id] = user.id
        await db.commit()
        lead_id = lead.id
    await seed_constellation_triage_form(factory)
    ticket = await env["create_ticket"]()
    from test_refine import assign_after_sales
    await assign_after_sales(env, ticket["id"])
    first = await env["client"].post(f"/api/v1/tickets/{ticket['id']}/triage-submit",
                                     json=triage_payload(after_sales_id, 2310, initial_opinion="售后初查"))
    assert first.status_code == 200, first.text
    star = first.json()["data"]
    assert star["category_id"] == 2310
    assert star["node_context"]["node_type"] == "triage"
    assert star["skill_group_name"] == "星座大系统负责人"
    assert star["callback_required"] is True
    return factory, ticket["id"], lead_id, users, after_sales_id


@pytest.mark.asyncio
@pytest.mark.parametrize("target_id,category_name,department", TARGETS)
async def test_constellation_triage_routes_each_direct_child(renv, target_id, category_name, department):
    factory, ticket_id, lead_id, users, after_sales_id = await setup_triage(renv)
    with as_user(lead_id, "handler"):
        detail = (await renv["client"].get(f"/api/v1/tickets/{ticket_id}")).json()
        form = detail["current_form"]
        assert form["code"] == "constellation_triage_v1" and form["version"] == 1
        assert [(field["field_key"], field["required"]) for field in form["fields"]] == [("initial_opinion", True)]
        options = detail["refine_options"]
        assert {option["id"] for option in options} == {2311, 2312, 2313}
        assert {option["id"]: option["next_department"] for option in options} == {
            2311: "软件开发组", 2312: "测运控组", 2313: "整星产品"}
        body = triage_payload(form["form_definition_id"], target_id, initial_opinion="负责人初查")
        missing = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json={**body, "values": {}})
        assert missing.status_code == 422
        no_target = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json={"form_definition_id": form["form_definition_id"], "form_version": 1,
                  "values": {"initial_opinion": "负责人初查"}})
        assert no_target.status_code == 422
        invalid_child = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json=triage_payload(form["form_definition_id"], 2302, initial_opinion="负责人初查"))
        assert invalid_child.status_code == 400
        forged = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json={**body, "target_department": "伪造部门"})
        assert forged.status_code == 422
        submitted = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json=body)
        assert submitted.status_code == 200, submitted.text
    result = submitted.json()["data"]
    assert result["category_id"] == target_id
    assert result["dispatch_chain_steps"] == [
        {"order": 1, "department_code": department},
        {"order": 2, "department_code": "售后", "stage": "phone_feedback"},
    ]
    assert result["dispatch_step_index"] == 0
    assert result["skill_group_name"] == department
    assert result["node_context"]["node_type"] == "processing"
    assert result["callback_required"] is True
    async with factory() as db:
        submissions = (await db.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket_id).order_by(TicketNodeSubmission.id))).scalars().all()
        assert len(submissions) == 2
        assert submissions[0].form_definition_id == after_sales_id
        assert submissions[1].data == {"initial_opinion": "负责人初查"}
        assert submissions[1].article_id is None
        assert not (await db.execute(select(Article).where(Article.ticket_id == ticket_id))).scalars().all()
    await renv["patch"](ticket_id, {"state": "open", "owner_id": users[target_id]})
    with as_user(users[target_id], "handler"):
        held = await renv["client"].patch(f"/api/v1/tickets/{ticket_id}", json={
            "state": "on_hold", "reason": "等待处理窗口",
            "hold_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
        assert held.status_code == 200, held.text
        resumed = await renv["client"].patch(f"/api/v1/tickets/{ticket_id}", json={
            "state": "open", "reason": "继续处理"})
        assert resumed.status_code == 200, resumed.text


@pytest.mark.asyncio
async def test_constellation_requires_target_chain_and_seed_is_idempotent(renv):
    factory, ticket_id, lead_id, _, _ = await setup_triage(renv)
    await seed_constellation_triage_form(factory)
    async with factory() as db:
        forms = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "constellation_triage_v1"))).scalars().all()
        assert len(forms) == 1
        bindings = (await db.execute(select(FormBinding).where(
            FormBinding.form_definition_id == forms[0].id))).scalars().all()
        assert len(bindings) == 1
        chain = (await db.execute(select(DispatchChain).where(DispatchChain.category_id == 2311))).scalar_one()
        chain.enabled = False
        await db.commit()
        form_id = forms[0].id
    with as_user(lead_id, "handler"):
        failed = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json=triage_payload(form_id, 2311, initial_opinion="负责人初查"))
        assert failed.status_code == 422
    async with factory() as db:
        assert (await db.get(Ticket, ticket_id)).category_id == 2310
