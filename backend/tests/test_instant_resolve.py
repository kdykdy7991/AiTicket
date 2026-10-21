"""Immediate consultation records an answer and archives without dispatch."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketStateLog
from test_v2_categories import _reseed_v2
from test_workflow_regression import _next_phone


async def test_instant_consult_creates_archived_ticket(client):
    http, _, engine = client
    await _reseed_v2(engine)
    response = await http.post("/api/v1/tickets", json={
        "intake_form": True, "category_id": 1205, "is_opportunity": False,
        "channel": "phone", "customer_phone": _next_phone(),
        "description": "咨询设备接入方式", "instant_resolution": "已告知接入步骤",
    })
    assert response.status_code == 201, response.text
    data = response.json()["data"]
    assert data["number"] and data["state"] == "archived"
    assert data["owner_id"] is None and data["dispatcher_id"] is None
    assert data["dispatch_chain_steps"] is None
    assert data["callback_required"] is False
    async with AsyncSession(engine) as db:
        ticket = await db.get(Ticket, data["id"])
        assert ticket.resolution == "已告知接入步骤"
        assert ticket.solution_deadline is None
        assert ticket.closed_at is not None and ticket.resolved is True
        logs = (await db.execute(select(TicketStateLog).where(TicketStateLog.ticket_id == ticket.id))).scalars().all()
        assert len(logs) == 1 and logs[0].action_type == "instant_resolve"


async def test_instant_consult_requires_answer_and_specific_category(client):
    http, _, engine = client
    await _reseed_v2(engine)
    base = {"intake_form": True, "category_id": 1205, "customer_phone": _next_phone(),
            "description": "如何使用", "is_opportunity": False}
    missing = await http.post("/api/v1/tickets", json=base)
    assert missing.status_code == 422
    unrelated = await http.post("/api/v1/tickets", json={**base, "category_id": 1202,
        "is_instant_resolve": True, "instant_resolution": "已答复"})
    assert unrelated.status_code == 422


async def test_instant_consult_draft_can_be_submitted(client):
    http, _, engine = client
    await _reseed_v2(engine)
    draft = await http.post("/api/v1/tickets", json={
        "is_draft": True, "category_id": 1205, "customer_phone": _next_phone(),
        "description": "咨询资费", "instant_resolution": "已说明资费",
    })
    assert draft.status_code == 201, draft.text
    submitted = await http.post(f"/api/v1/tickets/drafts/{draft.json()['data']['id']}/submit")
    assert submitted.status_code == 200, submitted.text
    assert submitted.json()["data"]["state"] == "archived"
