"""Resolution SLA uses category tiers and records each return-to-service attempt."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import TicketCategory


async def test_policy_api_validates_category_tier_and_uniqueness(client):
    http, _dispatcher, engine = client
    async with AsyncSession(engine) as db:
        root = TicketCategory(name="业务保障", level=1)
        db.add(root)
        await db.flush()
        root_id = root.id
        await db.commit()

    payload = {"category_id": root_id, "variant": "p1_urgent", "solution_minutes": 120}
    created = await http.post("/api/v1/sla-policies", json=payload)
    assert created.status_code == 201, created.text
    assert (await http.post("/api/v1/sla-policies", json=payload)).status_code == 409
    assert (await http.post("/api/v1/sla-policies", json={**payload, "variant": "一般"})).status_code == 422
    listed = (await http.get("/api/v1/sla-policies")).json()["data"]
    assert listed[0]["category_name"] == "业务保障"
    assert listed[0]["variant"] == "p1_urgent"


async def test_sla_round_restarts_after_customer_service_return(client):
    http, dispatcher_id, engine = client
    async with AsyncSession(engine) as db:
        root = TicketCategory(name="客户咨询", level=1)
        db.add(root)
        await db.flush()
        leaf = TicketCategory(name="产品咨询", parent_id=root.id, level=2)
        db.add(leaf)
        await db.flush()
        root_id, leaf_id = root.id, leaf.id
        await db.commit()
    policy = await http.post("/api/v1/sla-policies", json={
        "category_id": root_id, "variant": "default", "solution_minutes": 60,
    })
    assert policy.status_code == 201, policy.text
    created = await http.post("/api/v1/tickets", json={
        "description": "需要处理的问题", "category_id": leaf_id,
        "channel": "phone", "customer_type": "personal",
        "customer_phone": "13900005000", "dispatcher_id": dispatcher_id,
    })
    assert created.status_code == 201, created.text
    ticket_id = created.json()["data"]["id"]
    detail = (await http.get(f"/api/v1/tickets/{ticket_id}")).json()
    assert len(detail["sla_rounds"]) == 1
    assert detail["sla_rounds"][0]["status"] == "running"
    assert detail["solution_deadline"] is not None

    assigned = await http.patch(f"/api/v1/tickets/{ticket_id}", json={
        "state": "open", "owner_id": dispatcher_id,
    })
    assert assigned.status_code == 200, assigned.text
    resolved = await http.patch(f"/api/v1/tickets/{ticket_id}", json={"state": "resolved"})
    assert resolved.status_code == 200, resolved.text
    detail = (await http.get(f"/api/v1/tickets/{ticket_id}")).json()
    assert detail["sla_rounds"][0]["status"] == "delivered"
    assert detail["sla_rounds"][0]["ended_at"] is not None

    returned = await http.patch(f"/api/v1/tickets/{ticket_id}", json={
        "state": "open", "reason": "客服退回重新处理",
    })
    assert returned.status_code == 200, returned.text
    detail = (await http.get(f"/api/v1/tickets/{ticket_id}")).json()
    assert [round_["status"] for round_ in detail["sla_rounds"]] == ["delivered", "running"]
    assert detail["sla_rounds"][1]["sequence"] == 2
    assert datetime.fromisoformat(detail["sla_rounds"][1]["started_at"]) >= datetime.fromisoformat(detail["sla_rounds"][0]["ended_at"])


async def test_opportunity_never_starts_sla_round(client):
    http, _dispatcher, engine = client
    async with AsyncSession(engine) as db:
        root = TicketCategory(name="客户咨询", level=1)
        db.add(root)
        await db.flush()
        root_id = root.id
        await db.commit()
    assert (await http.post("/api/v1/sla-policies", json={
        "category_id": root_id, "variant": "default", "solution_minutes": 60,
    })).status_code == 201
    from app.models.ticket import Ticket
    from app.services.sla import start_round
    async with AsyncSession(engine) as db:
        ticket = Ticket(description="线索", category_id=root_id, is_opportunity=True,
                        customer_phone="13900005001", creator_id=1,
                        created_at=datetime.now(timezone.utc))
        db.add(ticket)
        await db.flush()
        assert await start_round(db, ticket) is None
        assert ticket.solution_deadline is None
        await db.rollback()


async def test_overdue_rate_excludes_opportunities_and_cancelled_tickets(client):
    http, _dispatcher, engine = client
    from app.models.ticket import Ticket
    created_at = datetime(2026, 7, 15, 4, 0, tzinfo=timezone.utc)
    async with AsyncSession(engine) as db:
        db.add_all([
            Ticket(number="SLA-1", description="普通超时", customer_phone="13900005100",
                   creator_id=1, created_at=created_at, solution_deadline=created_at + timedelta(minutes=60),
                   sla_solution_breached=True, is_opportunity=False, state="open"),
            Ticket(number="SLA-2", description="线索", customer_phone="13900005101",
                   creator_id=1, created_at=created_at, solution_deadline=created_at + timedelta(minutes=60),
                   sla_solution_breached=True, is_opportunity=True, state="archived"),
            Ticket(number="SLA-3", description="已撤销", customer_phone="13900005102",
                   creator_id=1, created_at=created_at, solution_deadline=created_at + timedelta(minutes=60),
                   sla_solution_breached=True, is_opportunity=False, state="cancelled"),
        ])
        await db.commit()
    response = await http.get("/api/v1/stats/service-analysis", params={
        "date_from": "2026-07-15", "date_to": "2026-07-15",
    })
    assert response.status_code == 200, response.text
    metrics = response.json()["data"]["metrics"]
    assert metrics["total"] == 3
    assert metrics["overdue_count"] == 1
    assert metrics["overdue_rate"] == 1.0
