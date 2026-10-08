"""Immediate consultations must not create ticket records."""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket


async def test_instant_resolve_rejected_without_ticket(client):
    c, _, engine = client
    async with AsyncSession(engine) as db:
        before = (await db.execute(select(func.count()).select_from(Ticket))).scalar_one()
    resp = await c.post("/api/v1/tickets", json={
        "description": "即时解答",
        "priority": "p4_enterprise",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900002001",
        "is_instant_resolve": True,
        "instant_resolution": "已答复",
    })
    assert resp.status_code == 422
    async with AsyncSession(engine) as db:
        after = (await db.execute(select(func.count()).select_from(Ticket))).scalar_one()
    assert after == before
