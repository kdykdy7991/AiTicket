"""工单列表导出应与筛选后的列表及逐列选择保持一致。"""

import csv
import io
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket


async def test_export_selected_columns_order_and_excludes_drafts(client):
    c, _dispatcher_id, engine = client
    when = datetime(2026, 10, 21, 1, 30, tzinfo=timezone.utc)
    async with AsyncSession(engine) as session:
        session.add_all([
            Ticket(number="EXPORT-1", customer_phone="13900000001", creator_id=1,
                   customer_name="甲客户", description="线索详情", is_opportunity=True,
                   created_at=when),
            Ticket(number="EXPORT-DRAFT", customer_phone="13900000002", creator_id=1,
                   customer_name="甲客户", is_draft=True, created_at=when),
        ])
        await session.commit()

    params = {
        "keyword": "甲客户",
        "columns": "description,number,is_opportunity,created_at",
    }
    response = await c.get("/api/v1/tickets/export", params=params)
    assert response.status_code == 200, response.text
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows == [
        ["客户问题详情", "工单号", "是否为线索工单", "受理时间"],
        ["线索详情", "EXPORT-1", "是", "2026-10-21 09:30"],
    ]

    listed = await c.get("/api/v1/tickets", params={"keyword": "甲客户"})
    assert listed.status_code == 200, listed.text
    assert listed.json()["pagination"]["total"] == len(rows) - 1


async def test_export_rejects_unknown_column(client):
    c, _dispatcher_id, _engine = client
    response = await c.get("/api/v1/tickets/export", params={"columns": "number,missing"})
    assert response.status_code == 422
