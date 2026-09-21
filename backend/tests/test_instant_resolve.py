"""Phase 6 tests: 即时办结咨询 (instant resolve) — formal ticket → archived.

Verify:
- POST /tickets with is_instant_resolve=true creates a formal ticket
  with full number / SLA / state_log, but lands in 'archived' immediately
- callback_required=False, is_callbacked=True (no callback needed)
- resolution, solved_at, closed_at are populated
- A single state_log entry captures the direct None→archived transition
- A subsequent attempt to transition the archived ticket fails
  (terminal state)
- is_instant_resolve=false (default) still creates a pending ticket
- A ticket without dispatcher_id can be instant-resolved (no need for
  department coordination in 咨询 case)
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.ticket import Ticket, TicketStateLog
from app.models.user import User


# ── Fixtures ─────────────────────────────────────────────────


@pytest_asyncio.fixture
async def ir_env(client):
    c, _dispatcher_id, engine = client
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        admin = (await s.execute(select(User).where(User.username == "ir_admin"))).scalar_one_or_none()
        if not admin:
            admin = User(username="ir_admin", name="即时管理员", password_hash="x", role="admin")
            s.add(admin)
            await s.commit()
            await s.refresh(admin)
    return {"client": c, "admin_id": admin.id, "engine": engine}


# ── Tests ────────────────────────────────────────────────────


async def test_instant_resolve_creates_archived_ticket(ir_env):
    c = ir_env["client"]
    resp = await c.post("/api/v1/tickets", json={
        "description": "客户咨询：如何使用A功能",
        "priority": "p4_enterprise",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900002001",
        "is_instant_resolve": True,
        "instant_resolution": "已告知客户操作步骤",
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    # Numbered like a formal ticket
    assert data["number"] is not None
    assert "-" in data["number"]
    # Landed in archived
    assert data["state"] == "archived"
    # No callback needed
    assert data["is_callbacked"] is True
    assert data["callback_required"] is False
    # Resolution recorded
    assert data["resolution"] == "已告知客户操作步骤"
    # Closed timestamps
    assert data["solved_at"] is not None
    assert data["closed_at"] is not None
    # warnings field carries the auto_match info
    w = resp.json()["warnings"]
    assert w is not None
    assert "即时办结" in w["auto_match_warning"]


async def test_instant_resolve_writes_state_log(ir_env):
    c = ir_env["client"]
    resp = await c.post("/api/v1/tickets", json={
        "description": "x",
        "priority": "p4_enterprise",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900002002",
        "is_instant_resolve": True,
        "instant_resolution": "已答复",
    })
    assert resp.status_code == 201
    ticket_id = resp.json()["data"]["id"]
    # Verify state_log
    factory = async_sessionmaker(ir_env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        logs = (await s.execute(
            select(TicketStateLog).where(TicketStateLog.ticket_id == ticket_id).order_by(TicketStateLog.id)
        )).scalars().all()
    assert len(logs) == 1
    assert logs[0].from_state is None
    assert logs[0].to_state == "archived"
    assert logs[0].reason == "即时办结咨询"
    # operator 是请求中的 get_current_user，不是 ir_admin（仅作 seed 用）
    assert logs[0].operator_id is not None


async def test_instant_resolve_works_without_dispatcher(ir_env):
    """即时办结咨询不必指定对接人。"""
    c = ir_env["client"]
    resp = await c.post("/api/v1/tickets", json={
        "description": "无对接人即时办结",
        "priority": "p4_enterprise",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900002003",
        "is_instant_resolve": True,
        "instant_resolution": "已答复",
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["dispatcher_id"] is None


async def test_default_create_still_pending(ir_env):
    """未指定 is_instant_resolve 时仍走 pending 流程（默认需 dispatcher_id）。"""
    c = ir_env["client"]
    factory = async_sessionmaker(ir_env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        # Need a dispatcher user (any active user).
        d = (await s.execute(select(User).where(User.is_active == True).limit(1))).scalar_one()
        d_id = d.id
    resp = await c.post("/api/v1/tickets", json={
        "description": "default",
        "priority": "p4_enterprise",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900002004",
        "dispatcher_id": d_id,
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["state"] == "pending"


async def test_archived_ticket_cannot_be_transitioned(ir_env):
    """archived 是终态，不能再 transition（Phase 6 之后的回归保护）。"""
    c = ir_env["client"]
    resp = await c.post("/api/v1/tickets", json={
        "description": "x",
        "priority": "p4_enterprise",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900002005",
        "is_instant_resolve": True,
        "instant_resolution": "done",
    })
    ticket_id = resp.json()["data"]["id"]
    # Try to PATCH state to open
    r = await c.patch(f"/api/v1/tickets/{ticket_id}", json={"state": "open"})
    # Expect 4xx (state transition error or business constraint)
    assert r.status_code >= 400, r.text


async def test_draft_create_still_works(ir_env):
    """草稿工单路径不被打扰。"""
    c = ir_env["client"]
    resp = await c.post("/api/v1/tickets", json={
        "description": "draft",
        "priority": "p4_enterprise",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900002006",
        "is_draft": True,
    })
    assert resp.status_code == 201
    data = resp.json()["data"]
    assert data["is_draft"] is True
    assert data["state"] == "pending"
    assert data["number"] is None