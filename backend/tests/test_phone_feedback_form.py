"""Published phone feedback form completes the existing feedback stage atomically."""

import asyncio
import json
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition, TicketNodeSubmission
from app.models.ticket import Article, ArticleAttachment, Ticket, TicketStateLog
from scripts.seed_phone_feedback_form import seed_phone_feedback_form
from test_processing_form import install_form, opened, submit as submit_processing
from test_transfer import tenv
from test_workflow_regression import as_user


async def install_feedback_form(env):
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    await seed_phone_feedback_form(factory)
    async with factory() as s:
        form = (await s.execute(select(FormDefinition).where(FormDefinition.code == "phone_feedback_v2"))).scalar_one()
        return form.id


async def feedback_open(env):
    processing_form = await install_form(env)
    feedback_form = await install_feedback_form(env)
    ticket, owner = await opened(env, 2298)
    assert (await submit_processing(env, ticket, processing_form, owner)).status_code == 200
    await env["patch"](ticket["id"], {"state": "open", "owner_id": env["aftersale_user"]})
    return await env["get"](ticket["id"]), feedback_form


def payload(ticket, form_id, **values):
    fields = {"phone_feedback_result": "已致电告知客户处理结果"}
    fields.update(values)
    return {"form_definition_id": form_id, "form_version": 2,
            "expected_category_id": ticket["category_id"],
            "expected_department_id": ticket["skill_group_id"],
            "expected_dispatch_step_index": ticket["dispatch_step_index"],
            "expected_state": ticket["state"], "values": fields}


async def submit(env, ticket, form_id, *, user_id=None, files=None, **values):
    with as_user(user_id or env["aftersale_user"], "handler"):
        return await env["client"].post(f"/api/v1/tickets/{ticket['id']}/node-submit",
            data={"payload": json.dumps(payload(ticket, form_id, **values))}, files=files or [])


@pytest.mark.asyncio
async def test_feedback_form_completion_and_history(tenv, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    ticket, form_id = await feedback_open(tenv)
    with as_user(tenv["aftersale_user"], "handler"):
        detail = await tenv["get"](ticket["id"])
        assert detail["node_context"]["node_type"] == "phone_feedback"
        assert detail["current_form"]["form_definition_id"] == form_id
        assert detail["current_form"]["code"] == "phone_feedback_v2"
        assert [field["field_key"] for field in detail["current_form"]["fields"]] == ["phone_feedback_result"]
        assert "can_note" not in detail and not detail["can_reply"]
        note = await tenv["client"].post(f"/api/v1/tickets/{ticket['id']}/articles",
            data={"type": "note", "body": "正在联系客户"})
        assert note.status_code == 422
        assert (await tenv["get"](ticket["id"]))["state"] == "open"
        bypass = await tenv["client"].post(f"/api/v1/tickets/{ticket['id']}/articles",
            data={"type": "reply", "body": "直接办结"})
        assert bypass.status_code == 409
    result = await submit(tenv, ticket, form_id,
        files=[("attachments", ("call-proof.png", b"image-data", "image/png"))])
    assert result.status_code == 200, result.text
    assert result.json()["data"]["state"] == "resolved"
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        records = (await s.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket["id"], TicketNodeSubmission.node_type == "phone_feedback"))).scalars().all()
        assert len(records) == 1
        record = records[0]
        assert record.data == {} and record.form_version == 2
        assert (await s.get(Article, record.article_id)).body == "已致电告知客户处理结果"
        assert len((await s.execute(select(ArticleAttachment).where(
            ArticleAttachment.article_id == record.article_id))).scalars().all()) == 1
        assert (await s.get(TicketStateLog, record.state_log_id)).action_type == "resolve"
    history = (await tenv["client"].get(f"/api/v1/tickets/{ticket['id']}/node-submissions")).json()
    assert any(r["article_body"] == "已致电告知客户处理结果" for r in history)
    assert next(r for r in history if r["node_type"] == "phone_feedback")["attachments"][0]["filename"] == "call-proof.png"


@pytest.mark.asyncio
async def test_feedback_required_options_permissions_and_replay(tenv):
    ticket, form_id = await feedback_open(tenv)
    assert (await submit(tenv, ticket, form_id, phone_feedback_result="")).status_code == 422
    assert (await submit(tenv, ticket, form_id, verification_status="passed")).status_code == 422
    assert (await submit(tenv, ticket, form_id, verification_conclusion="旧字段")).status_code == 422
    assert (await submit(tenv, ticket, form_id, user_id=tenv["platform_user"])).status_code == 403
    assert (await submit(tenv, ticket, form_id)).status_code == 200
    assert (await submit(tenv, ticket, form_id)).status_code == 409


@pytest.mark.asyncio
async def test_feedback_rolls_back_and_parallel_only_once(tenv):
    ticket, form_id = await feedback_open(tenv)
    with patch("app.api.v1.tickets.apply_transition", side_effect=RuntimeError("injected")):
        with pytest.raises(RuntimeError, match="injected"):
            await submit(tenv, ticket, form_id)
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        assert (await s.get(Ticket, ticket["id"])).state == "open"
        assert not (await s.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket["id"], TicketNodeSubmission.node_type == "phone_feedback"))).scalars().all()
    with as_user(tenv["aftersale_user"], "handler"):
        responses = await asyncio.gather(*(
            tenv["client"].post(f"/api/v1/tickets/{ticket['id']}/node-submit",
                data={"payload": json.dumps(payload(ticket, form_id))}) for _ in range(2)
        ))
    assert sorted(r.status_code for r in responses) == [200, 409]


@pytest.mark.asyncio
async def test_feedback_wrong_node_and_return_recomputes_context(tenv):
    processing_form = await install_form(tenv)
    feedback_form = await install_feedback_form(tenv)
    ticket, owner = await opened(tenv, 2298)
    assert (await submit(tenv, ticket, feedback_form, user_id=owner)).status_code == 409
    assert (await submit_processing(tenv, ticket, processing_form, owner)).status_code == 200
    pending = await tenv["get"](ticket["id"])
    assert pending["node_context"]["node_type"] == "phone_feedback"
    await tenv["patch"](ticket["id"], {"state": "returned", "reason": "需原部门复查"})
    returned = await tenv["get"](ticket["id"])
    assert returned["node_context"]["node_type"] == "processing"
    assert (await submit(tenv, pending, feedback_form)).status_code == 409


@pytest.mark.asyncio
async def test_v1_definition_retained_and_binding_switch_idempotent(tenv):
    form_id = await install_feedback_form(tenv)
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    await seed_phone_feedback_form(factory)
    async with factory() as s:
        forms = (await s.execute(select(FormDefinition).where(
            FormDefinition.code.in_(["phone_feedback_v1", "phone_feedback_v2"])
        ))).scalars().all()
        assert {form.code for form in forms} == {"phone_feedback_v1", "phone_feedback_v2"}
        v1 = next(form for form in forms if form.code == "phone_feedback_v1")
        v1_fields = (await s.execute(select(FormFieldDefinition).where(
            FormFieldDefinition.form_definition_id == v1.id))).scalars().all()
        assert {field.field_key for field in v1_fields} == {
            "verification_status", "verification_conclusion", "phone_feedback_result"}
        bindings = (await s.execute(select(FormBinding).where(
            FormBinding.node_type == "phone_feedback"))).scalars().all()
        assert len([binding for binding in bindings if binding.enabled]) == 1
        assert next(binding for binding in bindings if binding.enabled).form_definition_id == form_id


@pytest.mark.asyncio
async def test_existing_v1_binding_is_disabled_on_upgrade(tenv):
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    await seed_phone_feedback_form(factory)
    async with factory() as s:
        v1 = (await s.execute(select(FormDefinition).where(
            FormDefinition.code == "phone_feedback_v1"))).scalar_one()
        old_binding = FormBinding(node_type="phone_feedback", department_code=None,
                                  category_id=None, category_match_type="exact",
                                  form_definition_id=v1.id, priority=0, enabled=True)
        s.add(old_binding)
        await s.commit()
        old_id = old_binding.id
    await seed_phone_feedback_form(factory)
    async with factory() as s:
        assert (await s.get(FormBinding, old_id)).enabled is False
        current = (await s.execute(select(FormBinding).where(
            FormBinding.node_type == "phone_feedback", FormBinding.enabled.is_(True)))).scalars().all()
        assert len(current) == 1
        assert (await s.get(FormDefinition, current[0].form_definition_id)).code == "phone_feedback_v2"
