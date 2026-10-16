"""Sales tickets reuse node submission and the existing resolve/archive transitions."""

import json

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.group import SkillGroup, UserSkillGroup
from app.models.node_form import TicketNodeSubmission
from app.models.ticket import Article, Ticket, TicketStateLog
from app.models.user import User
from scripts.seed_sales_opportunity_form import PLACEHOLDER_NAME, PLACEHOLDER_USERNAME, seed_sales_opportunity_form
from test_workflow_regression import _next_phone, as_user


@pytest.mark.asyncio
async def test_sales_opportunity_create_submit_and_archive(client):
    http, _, engine = client
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await seed_sales_opportunity_form(factory)
    await seed_sales_opportunity_form(factory)
    async with factory() as db:
        sales = (await db.execute(select(SkillGroup).where(SkillGroup.name == "销售"))).scalar_one()
        placeholder = (await db.execute(select(User).where(
            User.username == PLACEHOLDER_USERNAME,
        ))).scalar_one()
        salesperson_id = placeholder.id
        assert placeholder.name == PLACEHOLDER_NAME
        assert placeholder.role == "handler" and placeholder.is_active
        memberships = (await db.execute(select(UserSkillGroup).where(
            UserSkillGroup.user_id == salesperson_id,
            UserSkillGroup.skill_group_id == sales.id,
        ))).scalars().all()
        assert len(memberships) == 1 and memberships[0].is_dispatcher
        assert (await db.execute(select(User).where(
            User.username == PLACEHOLDER_USERNAME,
        ))).scalars().all() == [placeholder]

    candidates = await http.get(f"/api/v1/skill-groups/{sales.id}/handlers")
    assert candidates.status_code == 200
    assert any(person["id"] == salesperson_id for person in candidates.json()["data"])

    create_payload = {
        "intake_form": True, "is_opportunity": True,
        "channel": "phone", "priority": "p4_enterprise",
        "customer_name": "客户", "customer_company": "公司", "industry": "智慧农业",
        "customer_phone": _next_phone(), "contact_phone": "13800138000",
        "description": "合作需求", "sales_owner_id": salesperson_id,
    }
    invalid_owner = await http.post("/api/v1/tickets", json={**create_payload, "sales_owner_id": 999999})
    assert invalid_owner.status_code == 422
    created = await http.post("/api/v1/tickets", json=create_payload)
    assert created.status_code == 201, created.text
    ticket_id = created.json()["data"]["id"]
    assert created.json()["data"]["dispatcher_id"] is None
    with as_user(salesperson_id, "handler"):
        detail = (await http.get(f"/api/v1/tickets/{ticket_id}")).json()
        assert detail["node_context"]["node_type"] == "sales_opportunity"
        assert detail["current_form"]["code"] == "sales_opportunity_v1"
        assert detail["can_note"] is True and detail["can_reply"] is False
        assert (await http.post(f"/api/v1/tickets/{ticket_id}/articles",
                                data={"type": "reply", "body": "绕过商机表单"})).status_code == 409
        assert (await http.post(f"/api/v1/tickets/{ticket_id}/articles",
                                data={"type": "note", "body": "联系客户中"})).status_code == 201
        form = detail["current_form"]
        base = {"form_definition_id": form["form_definition_id"], "form_version": form["version"],
                "expected_category_id": None, "expected_department_id": sales.id,
                "expected_dispatch_step_index": None, "expected_state": "open"}
        for values in ({"valid_opportunity": True, "customer_rating": "5"},
                       {"valid_opportunity": True, "customer_rating": "6", "sales_opinion": "已成交"}):
            rejected = await http.post(f"/api/v1/tickets/{ticket_id}/node-submit",
                data={"payload": json.dumps({**base, "values": values})})
            assert rejected.status_code == 422, rejected.text
        result = await http.post(f"/api/v1/tickets/{ticket_id}/node-submit",
            data={"payload": json.dumps({**base, "values": {
                "valid_opportunity": True, "customer_rating": "5", "sales_opinion": "已完成跟进",
            }})})
        assert result.status_code == 200, result.text
        assert result.json()["data"]["state"] == "archived"
        repeated = await http.post(f"/api/v1/tickets/{ticket_id}/node-submit",
            data={"payload": json.dumps({**base, "values": {
                "valid_opportunity": True, "customer_rating": "5", "sales_opinion": "已完成跟进",
            }})})
        assert repeated.status_code == 409

    async with factory() as db:
        ticket = await db.get(Ticket, ticket_id)
        assert ticket.owner_id == salesperson_id and ticket.closed_at is not None
        submissions = (await db.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket_id))).scalars().all()
        assert len(submissions) == 1
        assert submissions[0].data == {"valid_opportunity": True, "customer_rating": "5"}
        article = await db.get(Article, submissions[0].article_id)
        assert article.body == "已完成跟进"
        actions = (await db.execute(select(TicketStateLog.action_type).where(
            TicketStateLog.ticket_id == ticket_id).order_by(TicketStateLog.id))).scalars().all()
        assert actions == ["create", "dispatch", "resolve", "archive"]
