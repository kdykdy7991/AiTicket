"""回归测试：create_ticket / submit_draft 的人员快照 bug。

覆盖两个已修复的回归：
- AttributeError: 'TicketCreate' object has no attribute 'owner_id'（正式建单）
- NameError: submit_draft 引用了不存在的 body 变量（草稿提交）

注：is_draft 等状态走 DB 层断言——_ticket_to_brief() 漏传 is_draft 字段，
响应里恒为 False，不能信响应（该序列化 bug 另行处理）。
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket import Ticket, TicketStateLog


async def test_create_formal_ticket_writes_snapshot(client):
    """正式建单 -> 201，且 state_log 快照正确（不再 AttributeError）。"""
    c, dispatcher_id, engine = client
    resp = await c.post(
        "/api/v1/tickets",
        json={
            "customer_phone": "13800000000",
            "dispatcher_id": dispatcher_id,
            "is_draft": False,
        },
    )
    assert resp.status_code == 201, resp.text

    async with AsyncSession(engine) as s:
        log = (
            await s.execute(
                select(TicketStateLog).order_by(TicketStateLog.id.desc()).limit(1)
            )
        ).scalar_one()
        assert log.to_state == "pending"
        assert log.owner_id_snapshot is None  # 建单时无处理人
        assert log.dispatcher_id_snapshot == dispatcher_id


async def test_create_draft(client):
    """草稿建单 -> 201，DB 里 is_draft=True（不再走 _snapshot_people 分支）。"""
    c, _dispatcher_id, engine = client
    resp = await c.post(
        "/api/v1/tickets",
        json={"customer_phone": "13900000000", "is_draft": True},
    )
    assert resp.status_code == 201, resp.text

    async with AsyncSession(engine) as s:
        t = (
            await s.execute(select(Ticket).order_by(Ticket.id.desc()).limit(1))
        ).scalar_one()
        assert t.is_draft is True
        assert t.number is None  # 草稿无工单号


async def test_submit_draft(client):
    """草稿提交 -> 200（端点默认状态码），转正式且生成工单号（不再 NameError）。"""
    c, dispatcher_id, engine = client

    # 先建草稿（带 dispatcher_id，提交时必需）
    resp = await c.post(
        "/api/v1/tickets",
        json={
            "customer_phone": "13700000000",
            "dispatcher_id": dispatcher_id,
            "is_draft": True,
        },
    )
    assert resp.status_code == 201, resp.text
    draft_id = resp.json()["data"]["id"]

    # 提交草稿
    resp = await c.post(f"/api/v1/tickets/drafts/{draft_id}/submit")
    assert resp.status_code == 200, resp.text  # submit_draft 未显式设 201

    async with AsyncSession(engine) as s:
        t = (await s.execute(select(Ticket).where(Ticket.id == draft_id))).scalar_one()
        assert t.is_draft is False
        assert t.number is not None  # 提交后才生成工单号
