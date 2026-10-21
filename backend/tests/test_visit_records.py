"""来访记录是独立实体，保留历史工单标记但不会创建工单。"""

import csv
import io

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket


async def test_create_search_and_update_visit_without_ticket(client):
    c, _dispatcher_id, engine = client
    payload = {
        "contact_at": "2026-10-21T09:30:00+08:00",
        "contact_number": "13800000000",
        "customer_name": "测试来访",
        "service_agent": "谢文倩",
        "channel": "在线客服",
        "category_l1": "咨询类",
        "category_l2": "产品咨询",
        "registered_ticket": True,
        "fields": {"customer_source": "官网客服", "request": "询问产品"},
    }
    created = await c.post("/api/v1/visit-records", json=payload)
    assert created.status_code == 201, created.text
    record_id = created.json()["data"]["id"]

    listed = await c.get("/api/v1/visit-records", params={
        "keyword": "13800000000", "channel": "在线客服", "registered_ticket": True,
    })
    assert listed.status_code == 200, listed.text
    assert listed.json()["pagination"]["total"] == 1
    assert listed.json()["data"][0]["fields"]["request"] == "询问产品"

    exported = await c.get("/api/v1/visit-records/export", params={"channel": "在线客服"})
    assert exported.status_code == 200, exported.text
    csv_rows = list(csv.reader(io.StringIO(exported.content.decode("utf-8-sig"))))
    assert len(csv_rows) == 2
    assert csv_rows[0][:9] == ["原始Sheet", "原始行号", "渠道", "联系时间", "联系号码",
                               "姓名", "接待客服", "一级分类", "二级分类"]
    assert csv_rows[1][2:9] == ["在线客服", "2026-10-21 09:30:00", "13800000000",
                                 "测试来访", "谢文倩", "咨询类", "产品咨询"]

    payload["fields"]["request"] = "补充咨询内容"
    updated = await c.put(f"/api/v1/visit-records/{record_id}", json=payload)
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["fields"]["request"] == "补充咨询内容"
    async with AsyncSession(engine) as session:
        assert (await session.execute(select(func.count()).select_from(Ticket))).scalar_one() == 0
