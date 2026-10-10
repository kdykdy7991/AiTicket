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
