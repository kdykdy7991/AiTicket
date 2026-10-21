"""Sales selects a company-specific finance handler for reconciliation."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup
from app.models.ticket import Ticket
from app.models.user import User
from scripts.seed_sales_opportunity_form import seed_sales_opportunity_form
from scripts.seed_reconciliation_form import seed_reconciliation_form
from scripts.seed_processing_form import seed_processing_form
from test_v2_categories import _reseed_v2
from test_workflow_regression import _next_phone, as_user


@pytest.mark.asyncio
async def test_reconciliation_draft_submits_to_selected_sales(client):
    http, _, engine = client
    await _reseed_v2(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await seed_sales_opportunity_form(factory)
    async with factory() as db:
        sales = (await db.execute(select(User).where(User.username == "chenkeyi"))).scalar_one()
        sales_id = sales.id
    created = await http.post("/api/v1/tickets", json={
        "is_draft": True, "is_opportunity": False, "category_id": 2204,
        "customer_phone": _next_phone(), "sales_owner_id": sales_id,
    })
    assert created.status_code == 201, created.text
    draft_id = created.json()["data"]["id"]
    submitted = await http.post(f"/api/v1/tickets/drafts/{draft_id}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["state"] == "open"
    assert submitted.json()["data"]["owner_id"] == sales_id
    assert [step["department_code"] for step in submitted.json()["data"]["dispatch_chain_steps"]] == ["销售", "财务"]


@pytest.mark.asyncio
@pytest.mark.parametrize("company,person_name,username,wrong_name", [
    ("时空道宇", "姜敏", "jiangmin", "朱景升"),
    ("青岛上合", "朱景升", "zhujingsheng", "姜敏"),
])
async def test_reconciliation_sales_handoff_validates_company_and_finance_person(
    client, company, person_name, username, wrong_name,
):
    http, _, engine = client
    await _reseed_v2(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await seed_sales_opportunity_form(factory)
    await seed_reconciliation_form(factory)
    await seed_processing_form(factory)
    async with factory() as db:
        db.add(DispatchChain(category_id=2204, steps=[
            {"order": 1, "department_code": "销售"},
            {"order": 2, "department_code": "财务"},
        ], enabled=True))
        await db.commit()
        sales = (await db.execute(select(User).where(User.username == "chenkeyi"))).scalar_one()
        finance = (await db.execute(select(User).where(User.username == username))).scalar_one()
        sales_group = (await db.execute(select(SkillGroup).where(SkillGroup.name == "销售"))).scalar_one()
        finance_group = (await db.execute(select(SkillGroup).where(SkillGroup.name == "财务"))).scalar_one()
        sales_id, finance_id = sales.id, finance.id
        sales_group_id, finance_group_id = sales_group.id, finance_group.id

    payload = {
        "intake_form": True, "is_opportunity": False, "category_id": 2204,
        "customer_name": "客户甲", "customer_company": "客户单位", "industry": "智慧农业",
        "customer_phone": _next_phone(), "satellite_number": "SN-2204",
        "description": "申请业财对账", "sales_owner_id": sales_id,
    }
    missing_sales = await http.post("/api/v1/tickets", json={**payload, "sales_owner_id": None})
    assert missing_sales.status_code == 422
    created = await http.post("/api/v1/tickets", json=payload)
    assert created.status_code == 201, created.text
    ticket_id = created.json()["data"]["id"]
    assert created.json()["data"]["state"] == "open"
    assert created.json()["data"]["owner_id"] == sales_id
    assert created.json()["data"]["skill_group_id"] == sales_group_id

    with as_user(sales_id, "handler"):
        detail = (await http.get(f"/api/v1/tickets/{ticket_id}")).json()
        form = detail["current_form"]
        assert form["code"] == "reconciliation_sales_v1"
        base = {
            "form_definition_id": form["form_definition_id"], "form_version": form["version"],
            "expected_category_id": 2204, "expected_department_id": sales_group_id,
            "expected_dispatch_step_index": 0, "expected_state": "open",
        }
        values = {
            "reconciliation_customer_name": "客户甲", "project_order_number": "ORD-01",
            "finance_company": company, "finance_person": person_name,
            "processing_opinion": "资料已核对，请财务处理",
        }
        wrong = await http.post(f"/api/v1/tickets/{ticket_id}/node-submit",
            data={"payload": json.dumps({**base, "values": {**values, "finance_person": wrong_name}})})
        assert wrong.status_code == 422
        missing = await http.post(f"/api/v1/tickets/{ticket_id}/node-submit",
            data={"payload": json.dumps({**base, "values": {**values, "reconciliation_customer_name": ""}})})
        assert missing.status_code == 422
        submitted = await http.post(f"/api/v1/tickets/{ticket_id}/node-submit",
            data={"payload": json.dumps({**base, "values": values})})
        assert submitted.status_code == 200, submitted.text
        assert submitted.json()["data"]["state"] == "open"
        assert submitted.json()["data"]["owner_id"] == finance_id
        assert submitted.json()["data"]["skill_group_id"] == finance_group_id
        assert submitted.json()["data"]["dispatch_step_index"] == 1

    with as_user(finance_id, "handler"):
        detail = (await http.get(f"/api/v1/tickets/{ticket_id}")).json()
        form = detail["current_form"]
        assert form["code"] == "reconciliation_finance_v1"
        assert [field["field_key"] for field in form["fields"]] == ["processing_opinion"]
        assert detail["can_note"] is False
        base = {
            "form_definition_id": form["form_definition_id"], "form_version": form["version"],
            "expected_category_id": 2204, "expected_department_id": finance_group_id,
            "expected_dispatch_step_index": 1, "expected_state": "open",
        }
        missing_opinion = await http.post(f"/api/v1/tickets/{ticket_id}/node-submit",
            data={"payload": json.dumps({**base, "values": {"processing_opinion": ""}})})
        assert missing_opinion.status_code == 422
        completed = await http.post(f"/api/v1/tickets/{ticket_id}/node-submit",
            data={"payload": json.dumps({
                **base, "values": {"processing_opinion": "财务已完成处理"},
            })})
        assert completed.status_code == 200, completed.text
        assert completed.json()["data"]["state"] == "resolved"

    async with factory() as db:
        ticket = await db.get(Ticket, ticket_id)
        assert ticket.owner_id == finance_id
