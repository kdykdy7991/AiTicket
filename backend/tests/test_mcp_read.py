"""The MCP integration credential only exposes bounded read endpoints."""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.category import TicketCategory
from app.models.ticket import Ticket


async def test_mcp_read_auth_and_ticket_lookup(client, monkeypatch):
    c, _dispatcher_id, engine = client
    monkeypatch.setattr(settings, "MCP_INTERNAL_TOKEN", "integration-secret")
    async with AsyncSession(engine) as session:
        category = TicketCategory(name="业务保障")
        session.add(category)
        await session.flush()
        session.add(Ticket(
            number="20261009-0001", customer_phone="13900000000", creator_id=1,
            description="应用平台无法登录", category_id=category.id,
            created_at=datetime(2026, 10, 9, 8, 0, tzinfo=timezone.utc),
        ))
        session.add(Ticket(
            number="20261009-0002", customer_phone="13900000001", creator_id=1,
            description="另一张工单", category_id=category.id,
            created_at=datetime(2026, 10, 9, 9, 0, tzinfo=timezone.utc),
        ))
        await session.commit()

    base = "/api/v1/internal/mcp"
    assert (await c.get(f"{base}/tickets", params={"keyword": "应用平台"})).status_code == 401
    headers = {"Authorization": "Bearer integration-secret"}
    search = await c.get(f"{base}/tickets", params={"keyword": "应用平台"}, headers=headers)
    assert search.status_code == 200, search.text
    assert [row["number"] for row in search.json()["data"]] == ["20261009-0001"]
    assert "customer_phone" not in search.json()["data"][0]
    recent = await c.get(f"{base}/tickets/recent", params={"limit": 2}, headers=headers)
    assert recent.status_code == 200, recent.text
    assert [row["number"] for row in recent.json()["data"]] == ["20261009-0002", "20261009-0001"]
    assert (await c.get(f"{base}/tickets/recent", params={"limit": 21}, headers=headers)).status_code == 422
    detail = await c.get(f"{base}/tickets/20261009-0001", headers=headers)
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"]["category_path"] == "业务保障"
    categories = await c.get(f"{base}/categories", headers=headers)
    assert categories.json()["data"][0]["name"] == "业务保障"

    # The integration namespace has no write route.
    assert (await c.post(f"{base}/tickets", headers=headers)).status_code == 405
