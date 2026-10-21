"""First published node form: after-sales triage and atomic refine."""

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select

from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition, TicketNodeSubmission
from app.models.ticket import Ticket, TicketStateLog
from app.models.user import User
from app.services.node_context import resolve_node_context
from app.services.node_form import resolve_form
from scripts.seed_triage_form import FIELDS
from test_refine import assign_after_sales, async_sessionmaker_for, renv
from test_workflow_regression import as_user


async def install_form(env):
    factory = async_sessionmaker_for(env["engine"])
    async with factory() as s:
        star_group = SkillGroup(name="星座大系统负责人")
        star_user = User(username="triage-star-owner", name="星座负责人", password_hash="x", role="handler")
        s.add_all([star_group, star_user])
        await s.flush()
        s.add(UserSkillGroup(user_id=star_user.id, skill_group_id=star_group.id, is_dispatcher=True))
        s.add(DispatchChain(category_id=2310, steps=[{"order": 1, "department_code": "星座大系统负责人"}]))
        form = FormDefinition(code="after_sales_triage", name="售后分诊", node_type="triage",
                              version=1, enabled=True, published_at=None)
        s.add(form)
        await s.flush()
        for index, (key, label, kind, required, categories, storage, storage_key, limit) in enumerate(FIELDS):
            s.add(FormFieldDefinition(
                form_definition_id=form.id, field_key=key, label=label, field_type=kind,
                sort_order=index, required=required, options=None, validation={"max_length": limit},
                visibility_condition={"target_descendants_of_any": categories} if categories else None,
                required_condition=None, storage_type=storage, storage_key=storage_key,
            ))
        s.add(FormBinding(node_type="triage", department_code="售后", category_id=2301,
                          category_match_type="descendants_of", form_definition_id=form.id,
                          priority=0, enabled=True))
        await s.flush()
        form.published_at = datetime.now(timezone.utc)
        await s.commit()
        return form.id


def payload(form_id, target=2310, **values):
    return {"target_category_id": target, "form_definition_id": form_id,
            "form_version": 1, "values": values}


@pytest.mark.asyncio
async def test_triage_schema_submit_route_and_history(renv):
    form_id = await install_form(renv)
    c = renv["client"]
    ticket = await renv["create_ticket"]()
    await assign_after_sales(renv, ticket["id"])
    tid = ticket["id"]
    detail = (await c.get(f"/api/v1/tickets/{tid}")).json()
    assert detail["node_context"]["node_type"] == "triage"
    assert detail["current_form"]["form_definition_id"] == form_id
    assert [f["field_key"] for f in detail["current_form"]["fields"] if f["visible"]] == ["initial_opinion"]
    star = (await c.get(f"/api/v1/tickets/{tid}/current-form", params={"target_category_id": 2310})).json()
    visible = {f["field_key"] for f in star["fields"] if f["visible"]}
    assert visible == {"initial_opinion", "satellite_selection_rule", "obstruction_assessment"}
    assert (await c.post(f"/api/v1/tickets/{tid}/refine", json={"category_id": 2310})).status_code == 409
    assert (await c.post(f"/api/v1/tickets/{tid}/triage-submit", json=payload(form_id))).status_code == 422
    result = await c.post(f"/api/v1/tickets/{tid}/triage-submit", json=payload(
        form_id, initial_opinion="初查正常", satellite_selection_rule="优先北向", obstruction_assessment="无遮挡"))
    assert result.status_code == 200, result.text
    data = result.json()["data"]
    assert data["category_id"] == 2310
    assert data["state"] == "open"
    assert data["skill_group_name"] == "星座大系统负责人"
    assert data["dispatch_chain_steps"] == [{"order": 1, "department_code": "星座大系统负责人"}]
    assert data["node_context"]["node_type"] == "triage"
    factory = async_sessionmaker_for(renv["engine"])
    async with factory() as s:
        submissions = (await s.execute(select(TicketNodeSubmission).where(TicketNodeSubmission.ticket_id == tid))).scalars().all()
        logs = (await s.execute(select(TicketStateLog).where(TicketStateLog.ticket_id == tid, TicketStateLog.action_type == "refine"))).scalars().all()
        assert len(submissions) == len(logs) == 1
        assert submissions[0].state_log_id == logs[0].id
        assert submissions[0].data["initial_opinion"] == "初查正常"
        assert submissions[0].field_snapshot[0]["label"] == "初步核查意见"
    history = (await c.get(f"/api/v1/tickets/{tid}/node-submissions")).json()
    assert history[0]["form_code"] == "after_sales_triage"
    assert history[0]["form_name"] == "售后分诊"
    assert history[0]["operator_name"]
    assert history[0]["field_snapshot"][0]["label"] == "初步核查意见"
    assert history[0]["form_version"] == 1
    async with factory() as s:
        v2 = FormDefinition(code="after_sales_triage", name="新版分诊", node_type="triage",
                            version=2, enabled=True, published_at=datetime.now(timezone.utc))
        s.add(v2)
        await s.flush()
        s.add(FormBinding(node_type="triage", department_code="售后", category_id=2301,
                          category_match_type="descendants_of", form_definition_id=v2.id,
                          priority=1, enabled=True))
        await s.commit()
    old_history = (await c.get(f"/api/v1/tickets/{tid}/node-submissions")).json()
    assert old_history[0]["form_version"] == 1
    assert old_history[0]["field_snapshot"][0]["label"] == "初步核查意见"
    # The row lock and new category reject replay without a second submission.
    repeat = await c.post(f"/api/v1/tickets/{tid}/triage-submit", json=payload(form_id, initial_opinion="重复"))
    assert repeat.status_code in (400, 403)


@pytest.mark.asyncio
async def test_terminal_sn_is_ticket_field_and_failed_refine_rolls_back(renv):
    form_id = await install_form(renv)
    factory = async_sessionmaker_for(renv["engine"])
    async with factory() as s:
        s.add(TicketCategory(id=2321, parent_id=2301, name="终端研发", level=2, sort_order=5,
                             is_active=True, created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc)))
        await s.commit()
    c = renv["client"]
    ticket = await renv["create_ticket"]()
    await assign_after_sales(renv, ticket["id"])
    tid = ticket["id"]
    terminal = (await c.get(f"/api/v1/tickets/{tid}/current-form", params={"target_category_id": 2321})).json()
    visible = {f["field_key"] for f in terminal["fields"] if f["visible"]}
    assert {"device_sn", "terminal_name", "iccid", "imsi", "firmware_version", "host_software_type"} <= visible
    invalid = await c.post(f"/api/v1/tickets/{tid}/triage-submit", json=payload(
        form_id, 2311, initial_opinion="不能跳级", device_sn="SN-001"))
    assert invalid.status_code == 400
    async with factory() as s:
        assert not (await s.execute(select(TicketNodeSubmission).where(TicketNodeSubmission.ticket_id == tid))).scalars().all()
        assert (await s.get(Ticket, tid)).category_id == 2301
    result = await c.post(f"/api/v1/tickets/{tid}/triage-submit", json=payload(
        form_id, 2321, initial_opinion="设备异常", terminal_name="终端甲", device_sn="SN-001", iccid="ICCID-01"))
    assert result.status_code == 200, result.text
    async with factory() as s:
        saved = (await s.execute(select(TicketNodeSubmission).where(TicketNodeSubmission.ticket_id == tid))).scalar_one()
        assert saved.data["terminal_name"] == "终端甲"
        assert "device_sn" not in saved.data
        assert (await s.get(Ticket, tid)).device_sn == "SN-001"


@pytest.mark.asyncio
async def test_permission_version_and_binding_conflict(renv):
    form_id = await install_form(renv)
    c = renv["client"]
    ticket = await renv["create_ticket"]()
    await assign_after_sales(renv, ticket["id"])
    tid = ticket["id"]
    with as_user(renv["platform_user"], "handler"):
        denied = await c.post(f"/api/v1/tickets/{tid}/triage-submit", json=payload(form_id, initial_opinion="越权"))
    assert denied.status_code == 403
    stale = await c.post(f"/api/v1/tickets/{tid}/triage-submit", json={**payload(form_id, initial_opinion="过期"), "form_version": 2})
    assert stale.status_code == 409
    factory = async_sessionmaker_for(renv["engine"])
    async with factory() as s:
        s.add(FormBinding(node_type="triage", department_code="售后", category_id=2301,
                          category_match_type="descendants_of", form_definition_id=form_id,
                          priority=0, enabled=True))
        await s.commit()
    conflict = await c.get(f"/api/v1/tickets/{tid}/current-form", params={"target_category_id": 2310})
    assert conflict.status_code == 409


@pytest.mark.asyncio
async def test_ancestor_binding_exact_override_and_published_history(renv):
    form_id = await install_form(renv)
    ticket = await renv["create_ticket"]()
    await assign_after_sales(renv, ticket["id"])
    factory = async_sessionmaker_for(renv["engine"])
    async with factory() as s:
        current = await s.get(Ticket, ticket["id"])
        user = await s.get(User, renv["aftersale_user"])
        context = await resolve_node_context(s, current, user)
        inherited = await resolve_form(s, replace(context, category_id=2310))
        assert inherited.definition.id == form_id
        exact = FormDefinition(code="after_sales_triage", name="售后分诊 V2", node_type="triage",
                               version=2, enabled=True, published_at=datetime.now(timezone.utc))
        s.add(exact)
        await s.flush()
        s.add(FormBinding(node_type="triage", department_code="售后", category_id=2310,
                          category_match_type="exact", form_definition_id=exact.id,
                          priority=0, enabled=True))
        await s.commit()
        resolved = await resolve_form(s, replace(context, category_id=2310))
        assert resolved.definition.version == 2
        old = await s.get(FormDefinition, form_id)
        old.name = "篡改历史版本"
        with pytest.raises(ValueError, match="不可原地修改"):
            await s.flush()


@pytest.mark.asyncio
async def test_refine_failure_rolls_back_submission_and_ticket_field(renv):
    form_id = await install_form(renv)
    ticket = await renv["create_ticket"]()
    await assign_after_sales(renv, ticket["id"])
    tid = ticket["id"]
    with patch("app.api.v1.tickets.apply_refine", side_effect=RuntimeError("injected failure")):
        with pytest.raises(RuntimeError, match="injected failure"):
            await renv["client"].post(f"/api/v1/tickets/{tid}/triage-submit", json=payload(
                form_id, 2322, initial_opinion="检查完成", device_sn="SN-ROLLBACK"))
    factory = async_sessionmaker_for(renv["engine"])
    async with factory() as s:
        assert (await s.get(Ticket, tid)).category_id == 2301
        assert (await s.get(Ticket, tid)).device_sn is None
        assert not (await s.execute(select(TicketNodeSubmission).where(TicketNodeSubmission.ticket_id == tid))).scalars().all()


@pytest.mark.asyncio
async def test_parallel_triage_submissions_flow_only_once(renv):
    form_id = await install_form(renv)
    ticket = await renv["create_ticket"]()
    await assign_after_sales(renv, ticket["id"])
    tid = ticket["id"]
    body = payload(form_id, 2322, initial_opinion="并发核查")
    responses = await asyncio.gather(*(
        renv["client"].post(f"/api/v1/tickets/{tid}/triage-submit", json=body)
        for _ in range(2)
    ))
    assert sorted(r.status_code for r in responses) == [200, 403]
    factory = async_sessionmaker_for(renv["engine"])
    async with factory() as s:
        assert len((await s.execute(select(TicketNodeSubmission).where(TicketNodeSubmission.ticket_id == tid))).scalars().all()) == 1
        assert len((await s.execute(select(TicketStateLog).where(TicketStateLog.ticket_id == tid, TicketStateLog.action_type == "refine"))).scalars().all()) == 1
