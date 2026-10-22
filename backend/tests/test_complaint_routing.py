"""Phase 8 tests: complaint routing configuration (一般/重要/重大).

Verify:
- complaint_level on TicketCreate / TicketUpdate / TicketDetail
- complaint-specific SLA durations are matched directly by category and level
- historical tickets with NULL complaint_level still load normally
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.complaint import ComplaintEscalationPolicy
from app.models.category import TicketCategory
from app.models.sla import SLAPolicy
from app.models.user import User


@pytest_asyncio.fixture
async def cr_env(client):
    c, dispatcher_id, engine = client
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # The three complaint levels have independent resolution limits.
    async with factory() as s:
        root = TicketCategory(name="服务投诉", level=1)
        s.add(root)
        await s.flush()
        leaves = {}
        for level in ("一般", "重要", "重大"):
            leaf = TicketCategory(name=f"{level}投诉", parent_id=root.id, level=2)
            s.add(leaf)
            await s.flush()
            leaves[level] = leaf.id
        s.add_all([
            SLAPolicy(category_id=root.id, variant="一般", solution_minutes=240),
            SLAPolicy(category_id=root.id, variant="重要", solution_minutes=180),
            SLAPolicy(category_id=root.id, variant="重大", solution_minutes=120),
        ])
        # Re-seed complaint_escalation_policies after per-test TRUNCATE.
        from app.models.complaint import ComplaintEscalationPolicy
        existing = (await s.execute(
            select(ComplaintEscalationPolicy).where(
                ComplaintEscalationPolicy.complaint_level == "重大"
            )
        )).scalar_one_or_none()
        if not existing:
            now = datetime.now(timezone.utc)
            s.add_all([
                ComplaintEscalationPolicy(
                    complaint_level="一般",
                    required_role="agent", note="默认 一般", created_at=now, updated_at=now,
                ),
                ComplaintEscalationPolicy(
                    complaint_level="重要",
                    required_role="manager", note="默认 重要", created_at=now, updated_at=now,
                ),
                ComplaintEscalationPolicy(
                    complaint_level="重大",
                    required_role="admin", note="默认 重大", created_at=now, updated_at=now,
                ),
            ])
        await s.commit()
    return {"client": c, "engine": engine, "dispatcher_id": dispatcher_id, "leaves": leaves}


async def test_default_policies_seeded(cr_env):
    """投诉三级时限独立配置。"""
    factory = async_sessionmaker(cr_env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        rows = (await s.execute(select(SLAPolicy))).scalars().all()
    levels = {r.variant for r in rows}
    assert "一般" in levels
    assert "重要" in levels
    assert "重大" in levels


async def test_create_with_complaint_level_major_gets_shortened_sla(cr_env):
    """重大投诉直接匹配 120 分钟档。"""
    c = cr_env["client"]
    r = await c.post("/api/v1/tickets", json={
        "description": "重大投诉",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900004001",
        "dispatcher_id": cr_env["dispatcher_id"],
        "category_id": cr_env["leaves"]["重大"],
        "complaint_level": "重大",
    })
    assert r.status_code == 201, r.text
    data = r.json()["data"]
    assert data["complaint_level"] == "重大"
    # SLA is the directly configured 120 minutes.
    from datetime import datetime, timezone
    deadline = datetime.fromisoformat(data["solution_deadline"].replace("Z", "+00:00"))
    delta_min = (deadline - datetime.now(timezone.utc)).total_seconds() / 60
    # Allow up to 1 minute skew
    assert 118 <= delta_min <= 122


async def test_create_with_complaint_level_general_keeps_full_sla(cr_env):
    """一般投诉匹配独立的 240 分钟档。"""
    c = cr_env["client"]
    r = await c.post("/api/v1/tickets", json={
        "description": "一般投诉",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900004002",
        "dispatcher_id": cr_env["dispatcher_id"],
        "category_id": cr_env["leaves"]["一般"],
        "complaint_level": "一般",
    })
    assert r.status_code == 201, r.text
    from datetime import datetime, timezone
    deadline = datetime.fromisoformat(r.json()["data"]["solution_deadline"].replace("Z", "+00:00"))
    delta_min = (deadline - datetime.now(timezone.utc)).total_seconds() / 60
    # 240 minutes ± 1
    assert 238 <= delta_min <= 242


async def test_create_without_complaint_level_keeps_full_sla(cr_env):
    c = cr_env["client"]
    r = await c.post("/api/v1/tickets", json={
        "description": "普通工单",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900004003",
        "dispatcher_id": cr_env["dispatcher_id"],
    })
    assert r.status_code == 201, r.text
    assert r.json()["data"]["complaint_level"] is None


async def test_update_complaint_level(cr_env):
    c = cr_env["client"]
    r1 = await c.post("/api/v1/tickets", json={
        "description": "x",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900004004",
        "dispatcher_id": cr_env["dispatcher_id"],
    })
    tid = r1.json()["data"]["id"]
    r2 = await c.patch(f"/api/v1/tickets/{tid}", json={"complaint_level": "重要"})
    assert r2.status_code == 200, r2.text
    assert r2.json()["complaint_level"] == "重要"


async def test_historical_ticket_with_null_complaint_level_loads(cr_env):
    """历史工单 complaint_level=NULL, 加载/创建 SLA 不受影响。"""
    factory = async_sessionmaker(cr_env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        from app.models.ticket import Ticket
        now = datetime.now(timezone.utc)
        legacy = Ticket(
            number="20260101-7777",
            description="legacy complaint",
            priority="p3_normal",
            channel="phone",
            customer_type="personal",
            customer_phone="13900004005",
            state="open",
            dispatcher_id=cr_env["dispatcher_id"],
            creator_id=cr_env["dispatcher_id"],
            # complaint_level omitted => null
            created_at=now, updated_at=now,
        )
        s.add(legacy)
        await s.commit()
        legacy_id = legacy.id

    r = await cr_env["client"].get(f"/api/v1/tickets/{legacy_id}")
    assert r.status_code == 200
    assert r.json()["complaint_level"] is None
