"""V0.15 closure score and recognition remain independent of legacy satisfaction."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.node_form import FormBinding, FormDefinition, TicketNodeSubmission
from app.models.category import TicketCategory
from app.models.ticket import Ticket
from scripts.seed_closure_v4_form import seed_closure_v4_form
from test_closure_form import install_closure_form, resolved, payload, submit, REQUIRED_CATEGORY
from test_transfer import tenv
from test_workflow_regression import as_user


async def install_v4(env):
    v3_id = await install_closure_form(env)
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    await seed_closure_v4_form(factory)
    await seed_closure_v4_form(factory)
    async with factory() as db:
        v4 = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "closure_v4"))).scalar_one()
        v3 = await db.get(FormDefinition, v3_id)
        assert v3.code == "closure_v3" and v3.published_at is not None
        bindings = (await db.execute(select(FormBinding).where(
            FormBinding.node_type == "closure"))).scalars().all()
        assert len([binding for binding in bindings if binding.enabled]) == 1
        assert next(binding for binding in bindings if binding.enabled).form_definition_id == v4.id
        assert all(not binding.enabled for binding in bindings if binding.form_definition_id == v3_id)
        return v4.id


def v4_payload(ticket, form_id, **changes):
    body = payload(ticket, form_id)
    body["values"] = {
        "callback_completed": True,
        "customer_recognized": True,
        "closure_result": "recovered",
        **changes,
    }
    return body


async def submit_v4(env, ticket, form_id, **changes):
    with as_user(env["aftersale_user"], "agent"):
        return await env["client"].post(
            f"/api/v1/tickets/{ticket['id']}/closure-submit",
            json=v4_payload(ticket, form_id, **changes),
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [1, 10, None])
async def test_v4_score_bounds_and_no_legacy_mapping(tenv, score):
    form_id = await install_v4(tenv)
    ticket = await resolved(tenv)
    with as_user(tenv["aftersale_user"], "agent"):
        detail = await tenv["get"](ticket["id"])
    form = detail["current_form"]
    assert form["code"] == "closure_v4"
    fields = {field["field_key"]: field for field in form["fields"]}
    assert "satisfaction" not in fields
    assert fields["customer_satisfaction_score"]["field_type"] == "integer"
    assert fields["customer_satisfaction_score"]["min"] == 1
    assert fields["customer_satisfaction_score"]["max"] == 10
    assert fields["customer_recognized"]["boolean_labels"] == {"true": "认可", "false": "不认可"}
    updates = {} if score is None else {"customer_satisfaction_score": score}
    response = await submit_v4(tenv, ticket, form_id, **updates)
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["state"] == "archived"
    assert data["customer_satisfaction_score"] == score
    assert data["satisfaction"] is None
    assert data["customer_recognized"] is True
    assert data["callback_required"] is True and data["is_callbacked"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("score", [0, 11, 1.5, "5", True])
async def test_v4_rejects_invalid_score_without_conversion(tenv, score):
    form_id = await install_v4(tenv)
    ticket = await resolved(tenv)
    response = await submit_v4(tenv, ticket, form_id, customer_satisfaction_score=score)
    assert response.status_code == 422, response.text
    assert (await tenv["get"](ticket["id"]))["state"] == "resolved"


@pytest.mark.asyncio
async def test_v4_no_callback_or_incomplete_callback_hides_customer_fields(tenv):
    form_id = await install_v4(tenv)
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        (await db.get(TicketCategory, REQUIRED_CATEGORY)).requires_callback = False
        await db.commit()
    optional = await resolved(tenv, REQUIRED_CATEGORY)
    with as_user(tenv["aftersale_user"], "agent"):
        detail = await tenv["get"](optional["id"])
    assert detail["callback_required"] is False
    visible = {field["field_key"] for field in detail["current_form"]["fields"] if field["visible"]}
    assert visible == {"closure_result", "closure_result_note", "archive_notes"}
    body = v4_payload(optional, form_id)
    body["values"] = {"closure_result": "recovered"}
    with as_user(tenv["aftersale_user"], "agent"):
        no_callback = await tenv["client"].post(
            f"/api/v1/tickets/{optional['id']}/closure-submit", json=body)
    assert no_callback.status_code == 200, no_callback.text
    assert no_callback.json()["data"]["state"] == "archived"

    async with factory() as db:
        (await db.get(TicketCategory, REQUIRED_CATEGORY)).requires_callback = True
        await db.commit()
    required = await resolved(tenv, REQUIRED_CATEGORY)
    body = v4_payload(required, form_id)
    body["values"] = {"callback_completed": False, "closure_result": "recovered"}
    with as_user(tenv["aftersale_user"], "agent"):
        incomplete = await tenv["client"].post(
            f"/api/v1/tickets/{required['id']}/closure-submit", json=body)
    assert incomplete.status_code == 200, incomplete.text
    assert incomplete.json()["data"]["state"] == "resolved"
    assert incomplete.json()["data"]["customer_satisfaction_score"] is None
    assert incomplete.json()["data"]["callback_required"] is True
    assert incomplete.json()["data"]["is_callbacked"] is False


@pytest.mark.asyncio
async def test_v4_unrecognized_requires_reason_and_blocks_archive(tenv):
    form_id = await install_v4(tenv)
    ticket = await resolved(tenv)
    missing = await submit_v4(tenv, ticket, form_id, customer_recognized=False)
    assert missing.status_code == 422
    recorded = await submit_v4(tenv, ticket, form_id, customer_recognized=False,
                               customer_satisfaction_score=10, unsatisfied_reason="问题仍未解决")
    assert recorded.status_code == 200, recorded.text
    data = recorded.json()["data"]
    assert data["state"] == "resolved"
    assert data["customer_recognized"] is False
    assert data["customer_satisfaction_score"] == 10
    assert data["unsatisfied_reason"] == "问题仍未解决"
    assert data["satisfaction"] is None
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        submission = (await db.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket["id"]))).scalar_one()
        assert submission.action_type == "callback_record"
        assert submission.data == {}


@pytest.mark.asyncio
async def test_v4_preserves_legacy_dissatisfied_archive_guard(tenv):
    form_id = await install_v4(tenv)
    ticket = await resolved(tenv)
    await tenv["patch"](ticket["id"], {
        "is_callbacked": True, "satisfaction": "dissatisfied",
        "unsatisfied_reason": "旧四档评价不满意",
    })
    detail = await tenv["get"](ticket["id"])
    assert detail["current_form"] is None
    forbidden = await tenv["client"].patch(f"/api/v1/tickets/{ticket['id']}", json={"state": "archived"})
    assert forbidden.status_code == 409 or forbidden.status_code == 422
    async with async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)() as db:
        stored = await db.get(Ticket, ticket["id"])
        assert stored.satisfaction == "dissatisfied"
        assert stored.customer_satisfaction_score is None


@pytest.mark.asyncio
async def test_v4_does_not_overwrite_existing_legacy_satisfaction(tenv):
    form_id = await install_v4(tenv)
    ticket = await resolved(tenv)
    await tenv["patch"](ticket["id"], {"is_callbacked": True, "satisfaction": "average"})
    response = await submit_v4(tenv, ticket, form_id, customer_satisfaction_score=1)
    assert response.status_code == 200, response.text
    assert response.json()["data"]["satisfaction"] == "average"
    assert response.json()["data"]["customer_satisfaction_score"] == 1
