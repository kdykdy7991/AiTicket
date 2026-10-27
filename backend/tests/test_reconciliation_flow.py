"""Reconciliation: intake -> management review -> finance, without sales selection."""
import json

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.group import SkillGroup, UserSkillGroup
from app.models.user import User
from scripts.seed_reconciliation_form import seed_reconciliation_form
from test_v2_categories import _reseed_v2
from test_workflow_regression import _next_phone, as_user


@pytest.mark.asyncio
@pytest.mark.parametrize("draft", [False, True])
async def test_reconciliation_review_finance(client, draft):
    http, _, engine = client
    await _reseed_v2(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await seed_reconciliation_form(factory)
    await seed_reconciliation_form(factory)  # Publishing forms is idempotent.
    async with factory() as db:
        review = SkillGroup(name="经营管理部")
        finance = SkillGroup(name="财务")
        reviewer = User(username="yibo", name="易波", role="handler", password_hash="x")
        accountant = User(username="lianlu", name="练露", role="handler", password_hash="x")
        db.add_all([review, finance, reviewer, accountant])
        await db.flush()
        db.add_all([UserSkillGroup(user_id=reviewer.id, skill_group_id=review.id, is_dispatcher=True),
                    UserSkillGroup(user_id=accountant.id, skill_group_id=finance.id, is_dispatcher=True)])
        await db.commit()
        review_id, finance_id, reviewer_id, accountant_id = review.id, finance.id, reviewer.id, accountant.id
    # Ordinary agent, rather than admin, must also be able to submit intake.
    with as_user(1, "agent"):
        created = await http.post("/api/v1/tickets", json={
            "intake_form": True, "is_draft": draft, "is_opportunity": False, "category_id": 2204,
            "customer_name": "客户甲", "customer_company": "客户单位", "industry": "智慧农业",
            "customer_phone": _next_phone(), "satellite_number": "SN-2204",
            "description": "申请业财对账",
        })
        assert created.status_code == 201, created.text
        ticket_id = created.json()["data"]["id"]
        if draft:
            detail = await http.get(f"/api/v1/tickets/{ticket_id}")
            assert detail.status_code == 200, detail.text
            edited = await http.patch(f"/api/v1/tickets/drafts/{ticket_id}", json={
                "is_draft": True, "is_opportunity": False, "category_id": 2204,
                "customer_phone": _next_phone(), "description": "草稿修改",
            })
            assert edited.status_code == 200, edited.text
            detail = await http.get(f"/api/v1/tickets/{ticket_id}")
            assert detail.status_code == 200, detail.text
            created = await http.post(f"/api/v1/tickets/drafts/{ticket_id}/submit")
            assert created.status_code == 200, created.text
    ticket = created.json()["data"]
    assert ticket["state"] == "open"
    assert ticket["owner_id"] == reviewer_id
    assert ticket["skill_group_id"] == review_id
    assert [s["department_code"] for s in ticket["dispatch_chain_steps"]] == ["经营管理部", "财务"]
    initial_detail = (await http.get(f"/api/v1/tickets/{ticket_id}/state-logs")).json()
    assert [log["action_type"] for log in initial_detail["data"]] == ["create", "auto_assign"]
    for index, owner_id, group_id, code in [
        (0, reviewer_id, review_id, "reconciliation_review_v1"),
        (1, accountant_id, finance_id, "reconciliation_finance_v1"),
    ]:
        with as_user(owner_id, "handler"):
            detail = (await http.get(f"/api/v1/tickets/{ticket_id}")).json()
            form = detail["current_form"]
            assert form["code"] == code
            assert detail["node_context"]["node_name"] == form["name"]
            with as_user(1, "admin"):
                readonly = (await http.get(f"/api/v1/tickets/{ticket_id}")).json()
                assert readonly["node_context"]["node_name"] == form["name"]
                assert readonly["current_form"] is None
            if index == 0:
                assert form["name"] == "经管审核"
            assert [f["field_key"] for f in form["fields"]] == ["processing_opinion"]
            base = {"form_definition_id": form["form_definition_id"], "form_version": form["version"],
                    "expected_category_id": 2204, "expected_department_id": group_id,
                    "expected_dispatch_step_index": index, "expected_state": "open"}
            for opinion in ("", "   "):
                missing = await http.post(f"/api/v1/tickets/{ticket_id}/node-submit",
                    data={"payload": json.dumps({**base, "values": {"processing_opinion": opinion}})})
                assert missing.status_code == 422, missing.text
            submitted = await http.post(f"/api/v1/tickets/{ticket_id}/node-submit",
                data={"payload": json.dumps({**base, "values": {"processing_opinion": "核对无误"}})})
            assert submitted.status_code == 200, submitted.text
            result = submitted.json()["data"]
            assert result["state"] == ("open" if index == 0 else "resolved")
            assert result["owner_id"] == accountant_id
            assert result["skill_group_id"] == finance_id

    history = (await http.get(f"/api/v1/tickets/{ticket_id}/state-logs")).json()["data"]
    assert "dispatch" not in {log["action_type"] for log in history}
    assert [log["action_type"] for log in history].count("auto_assign") == 2

    submissions = (await http.get(f"/api/v1/tickets/{ticket_id}/node-submissions")).json()
    assert submissions[0]["form_name"] == "经管审核"
    assert submissions[1]["form_name"] == "业财对账财务处理"
