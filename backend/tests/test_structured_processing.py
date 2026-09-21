"""Phase 7 tests: tickets.root_cause and tickets.solution fields.

- Verify they're set when constructed via TicketCreate (with null default)
- Verify PATCH can update them
- Verify they're exposed in TicketDetail
- Verify historical tickets with null values still load correctly
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.user import User
from app.models.category import TicketCategory


@pytest_asyncio.fixture
async def sp_env(client):
    c, dispatcher_id, engine = client
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        # Pre-create category to satisfy v2 category_ids (just to avoid FK issues).
        now = datetime.now(timezone.utc)
        cat = (await s.execute(select(TicketCategory).where(TicketCategory.id == 7001))).scalar_one_or_none()
        if not cat:
            cat = TicketCategory(
                id=7001, parent_id=None, name="SP分类", level=1,
                sort_order=0, is_active=True, created_at=now, updated_at=now,
            )
            s.add(cat)
            await s.commit()
    return {"client": c, "engine": engine, "dispatcher_id": dispatcher_id, "category_id": 7001}


async def test_create_with_root_cause_and_solution(sp_env):
    c = sp_env["client"]
    resp = await c.post("/api/v1/tickets", json={
        "description": "x",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900003001",
        "dispatcher_id": sp_env["dispatcher_id"],
        "root_cause": "网络抖动导致链路中断",
        "solution": "切换至备用链路并监控",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["root_cause"] == "网络抖动导致链路中断"
    assert data["solution"] == "切换至备用链路并监控"


async def test_create_without_root_cause_solution_defaults_null(sp_env):
    c = sp_env["client"]
    resp = await c.post("/api/v1/tickets", json={
        "description": "x",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900003002",
        "dispatcher_id": sp_env["dispatcher_id"],
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["root_cause"] is None
    assert data["solution"] is None


async def test_update_root_cause_and_solution(sp_env):
    c = sp_env["client"]
    r1 = await c.post("/api/v1/tickets", json={
        "description": "x",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900003003",
        "dispatcher_id": sp_env["dispatcher_id"],
    })
    tid = r1.json()["data"]["id"]
    r2 = await c.patch(f"/api/v1/tickets/{tid}", json={
        "root_cause": "硬件版本不兼容",
        "solution": "升级固件",
    })
    assert r2.status_code == 200, r2.text
    assert r2.json()["root_cause"] == "硬件版本不兼容"
    assert r2.json()["solution"] == "升级固件"


async def test_historical_ticket_with_null_loads_normally(sp_env):
    """历史工单没有 root_cause / solution：详情仍正常返回（null）。"""
    factory = async_sessionmaker(sp_env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        from app.models.ticket import Ticket
        now = datetime.now(timezone.utc)
        legacy = Ticket(
            number="20260101-9999",
            description="legacy",
            priority="p3_normal",
            channel="phone",
            customer_type="personal",
            customer_phone="13900003004",
            state="open",
            category_id=sp_env["category_id"],
            dispatcher_id=sp_env["dispatcher_id"],
            creator_id=sp_env["dispatcher_id"],
            # root_cause / solution omitted => null
            created_at=now, updated_at=now,
        )
        s.add(legacy)
        await s.commit()
        legacy_id = legacy.id

    r = await sp_env["client"].get(f"/api/v1/tickets/{legacy_id}")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["root_cause"] is None
    assert data["solution"] is None