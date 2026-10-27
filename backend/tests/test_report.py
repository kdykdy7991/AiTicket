"""报表 period 参数回归测试。

前端选自定义日期范围时会传 period=custom，后端 Query 的 pattern 曾漏掉
custom，导致 422 校验失败、前端报错。
"""

from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import TicketCategory
from app.models.ticket import Ticket


async def test_report_custom_period(client):
    """period=custom + 显式日期范围 -> 200（不再 422）。"""
    c, _dispatcher_id, _engine = client
    resp = await c.get(
        "/api/v1/stats/report",
        params={"period": "custom", "date_from": "2026-07-01", "date_to": "2026-07-29"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["date_from"] == "2026-07-01"
    assert data["date_to"] == "2026-07-29"


async def test_report_groups_deep_and_direct_tickets_under_root(client):
    c, _dispatcher_id, engine = client
    async with AsyncSession(engine) as session:
        roots = [TicketCategory(name=name) for name in ("客户咨询", "业务保障")]
        session.add_all(roots)
        await session.flush()
        second = TicketCategory(name="星座大系统", parent_id=roots[1].id, level=2)
        session.add(second)
        await session.flush()
        leaf = TicketCategory(name="应用平台", parent_id=second.id, level=3)
        session.add(leaf)
        await session.flush()
        for index, category in enumerate((roots[1], leaf), start=1):
            session.add(Ticket(
                number=f"RPT-{index}", customer_phone="13900000000", creator_id=1,
                category_id=category.id,
                created_at=datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc),
            ))
        await session.commit()

    resp = await c.get("/api/v1/stats/report", params={
        "period": "custom", "date_from": "2026-07-15", "date_to": "2026-07-15",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert {row["name"]: row["count"] for row in data["by_category"]} == {
        "客户咨询": 0, "业务保障": 2,
    }
    assert {row["name"]: row["count"] for row in data["by_subcategory"]["业务保障"]} == {
        "待确定二级分类": 1, "星座大系统": 1,
    }
    assert next(row for row in data["by_category"] if row["name"] == "业务保障")["trend"][0]["value"] == 2


async def test_service_analysis_uses_real_tickets_and_separates_opportunities(client):
    c, _dispatcher_id, engine = client
    when = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    async with AsyncSession(engine) as session:
        root = TicketCategory(name="业务保障")
        session.add(root)
        await session.flush()
        session.add_all([
            Ticket(number="SVC-1", customer_phone="13900000000", creator_id=1,
                   category_id=root.id, is_opportunity=False, created_at=when),
            Ticket(number="OPP-1", customer_phone="13900000001", creator_id=1,
                   is_opportunity=True, created_at=when),
            Ticket(number="DRAFT-1", customer_phone="13900000002", creator_id=1,
                   is_draft=True, created_at=when),
        ])
        await session.commit()

    resp = await c.get("/api/v1/stats/service-analysis", params={
        "date_from": "2026-07-15", "date_to": "2026-07-15",
    })
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["metrics"]["total"] == 2
    assert data["metrics"]["service_count"] == 1
    assert data["metrics"]["opportunity_count"] == 1
    assert {row["name"]: row["count"] for row in data["by_category"]} == {
        "业务保障": 1, "线索工单": 1,
    }


async def test_report_closure_rate_counts_only_archived_service_tickets(client):
    c, _dispatcher_id, engine = client
    when = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)
    async with AsyncSession(engine) as session:
        session.add_all([
            Ticket(number="CLOSED-SERVICE", customer_phone="13900000001", creator_id=1,
                   state="archived", is_opportunity=False, customer_recognized=True, created_at=when),
            Ticket(number="OPEN-SERVICE", customer_phone="13900000002", creator_id=1,
                   state="open", is_opportunity=False, satisfaction="satisfied", created_at=when),
            Ticket(number="CANCELLED-SERVICE", customer_phone="13900000003", creator_id=1,
                   state="cancelled", is_opportunity=False, created_at=when),
            Ticket(number="CLOSED-LEAD", customer_phone="13900000004", creator_id=1,
                   state="archived", is_opportunity=True, customer_recognized=True, created_at=when),
        ])
        await session.commit()

    response = await c.get("/api/v1/stats/service-analysis", params={
        "date_from": "2026-07-15", "date_to": "2026-07-15",
    })
    assert response.status_code == 200, response.text
    metrics = response.json()["data"]["metrics"]
    assert metrics["total"] == 4
    assert metrics["service_count"] == 3
    assert metrics["closed_count"] == 1
    assert metrics["closure_rate"] == 0.3333
    assert metrics["satisfied_count"] == 1
    assert metrics["rated_count"] == 1
    assert metrics["satisfaction_rate"] == 0.3333
