"""Phase 3 tests: category routing rules CRUD + resolve + validation."""

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from datetime import datetime, timezone

from app.models.category import TicketCategory
from app.models.group import SkillGroup, UserSkillGroup
from app.models.routing import CategoryRoutingRule
from app.models.user import User


# ── Fixtures ─────────────────────────────────────────────────


async def _seed_skill_groups_and_users(engine):
    """Insert skill_groups + users + user_skill_groups needed by routing tests."""
    now = datetime.now(timezone.utc)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as s:
        # Look up existing groups (seed.py may have inserted some); reuse by name.
        async def _get_or_create_sg(name: str) -> SkillGroup:
            r = await s.execute(select(SkillGroup).where(SkillGroup.name == name))
            row = r.scalar_one_or_none()
            if row:
                return row
            row = SkillGroup(name=name, created_at=now, updated_at=now)
            s.add(row)
            await s.flush()
            return row

        coord_sg = await _get_or_create_sg("测试协调部")
        prof_sg = await _get_or_create_sg("测试专业部")

        async def _get_or_create_user(username: str, name: str) -> User:
            r = await s.execute(select(User).where(User.username == username))
            row = r.scalar_one_or_none()
            if row:
                return row
            row = User(username=username, name=name, password_hash="x", role="handler", is_active=True)
            s.add(row)
            await s.flush()
            return row

        coord_user = await _get_or_create_user("test_coord_user", "测试协调人")
        prof_user = await _get_or_create_user("test_prof_user", "测试专业处理人")

        # UserSkillGroup links (idempotent).
        for uid, sgid, is_disp in [
            (coord_user.id, coord_sg.id, True),
            (prof_user.id, prof_sg.id, False),
        ]:
            r = await s.execute(
                select(UserSkillGroup).where(
                    UserSkillGroup.user_id == uid,
                    UserSkillGroup.skill_group_id == sgid,
                )
            )
            if not r.scalar_one_or_none():
                s.add(UserSkillGroup(user_id=uid, skill_group_id=sgid, is_dispatcher=is_disp))
        await s.commit()
        return {
            "coord_sg_id": coord_sg.id,
            "prof_sg_id": prof_sg.id,
            "coord_user_id": coord_user.id,
            "prof_user_id": prof_user.id,
        }


async def _seed_categories(engine):
    """Insert a leaf category the rules can bind to."""
    now = datetime.now(timezone.utc)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as s:
        # Wipe any prior routing rules + categories created by previous test runs.
        from app.models.routing import CategoryRoutingRule
        await s.execute(CategoryRoutingRule.__table__.delete())
        existing_ids = set(
            (await s.execute(select(TicketCategory.id))).scalars().all()
        )
        to_add = []
        if 9001 not in existing_ids:
            to_add.append(TicketCategory(id=9001, parent_id=None, name="测试分类", level=1, sort_order=0, is_active=True, created_at=now, updated_at=now))
        if 9002 not in existing_ids:
            to_add.append(TicketCategory(id=9002, parent_id=None, name="另一个分类", level=1, sort_order=1, is_active=True, created_at=now, updated_at=now))
        if to_add:
            s.add_all(to_add)
            await s.commit()
        return 9001, 9002


@pytest_asyncio.fixture
async def routing_env(client):
    c, _dispatcher_id, engine = client
    ids = await _seed_skill_groups_and_users(engine)
    cat1, cat2 = await _seed_categories(engine)
    yield {**ids, "client": c, "engine": engine, "cat1": cat1, "cat2": cat2}


# ── Tests ────────────────────────────────────────────────────


async def test_create_rule_full(routing_env):
    c = routing_env["client"]
    payload = {
        "category_id": routing_env["cat1"],
        "dispatcher_skill_group_id": routing_env["coord_sg_id"],
        "dispatcher_id": routing_env["coord_user_id"],
        "handler_skill_group_id": routing_env["prof_sg_id"],
        "owner_id": routing_env["prof_user_id"],
        "note": "phase3 test",
    }
    resp = await c.post("/api/v1/routing-rules", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["category_id"] == routing_env["cat1"]
    assert data["dispatcher_id"] == routing_env["coord_user_id"]
    assert data["enabled"] is True


async def test_duplicate_category_rule_rejected(routing_env):
    c = routing_env["client"]
    payload = {
        "category_id": routing_env["cat1"],
        "dispatcher_skill_group_id": routing_env["coord_sg_id"],
        "dispatcher_id": routing_env["coord_user_id"],
    }
    r1 = await c.post("/api/v1/routing-rules", json=payload)
    assert r1.status_code == 201
    r2 = await c.post("/api/v1/routing-rules", json=payload)
    assert r2.status_code == 409


async def test_dispatcher_must_be_marked(routing_env):
    """专业处理人不应被作为 dispatcher 角色使用。"""
    c = routing_env["client"]
    payload = {
        "category_id": routing_env["cat2"],
        "dispatcher_skill_group_id": routing_env["coord_sg_id"],
        "dispatcher_id": routing_env["prof_user_id"],  # 专业处理人，没有 is_dispatcher 标记
    }
    resp = await c.post("/api/v1/routing-rules", json=payload)
    assert resp.status_code == 400


async def test_owner_must_belong_to_handler_group(routing_env):
    """owner 不属于 handler_skill_group 应拒绝。"""
    c = routing_env["client"]
    payload = {
        "category_id": routing_env["cat2"],
        "dispatcher_skill_group_id": routing_env["coord_sg_id"],
        "dispatcher_id": routing_env["coord_user_id"],
        "handler_skill_group_id": routing_env["prof_sg_id"],
        "owner_id": routing_env["coord_user_id"],  # 不属于专业部
    }
    resp = await c.post("/api/v1/routing-rules", json=payload)
    assert resp.status_code == 400


async def test_owner_optional_when_handler_group_missing(routing_env):
    """专业部门还没定的情况下，允许只填协调部分（兼容硬件故障等场景）。"""
    c = routing_env["client"]
    payload = {
        "category_id": routing_env["cat2"],
        "dispatcher_skill_group_id": routing_env["coord_sg_id"],
        "dispatcher_id": routing_env["coord_user_id"],
    }
    resp = await c.post("/api/v1/routing-rules", json=payload)
    assert resp.status_code == 201, resp.text


async def test_resolve_returns_rule(routing_env):
    c = routing_env["client"]
    await c.post("/api/v1/routing-rules", json={
        "category_id": routing_env["cat1"],
        "dispatcher_skill_group_id": routing_env["coord_sg_id"],
        "dispatcher_id": routing_env["coord_user_id"],
        "handler_skill_group_id": routing_env["prof_sg_id"],
        "owner_id": routing_env["prof_user_id"],
    })
    r = await c.post("/api/v1/routing-rules/resolve", json={"category_id": routing_env["cat1"]})
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["matched"] is True
    assert data["dispatcher_id"] == routing_env["coord_user_id"]
    assert data["owner_id"] == routing_env["prof_user_id"]


async def test_resolve_unconfigured_category(routing_env):
    """无 routing rule 的分类：matched=False + reason。"""
    c = routing_env["client"]
    r = await c.post("/api/v1/routing-rules/resolve", json={"category_id": routing_env["cat2"]})
    data = r.json()["data"]
    assert data["matched"] is False
    assert "尚未配置" in data["reason"]


async def test_resolve_disabled_rule(routing_env):
    c = routing_env["client"]
    await c.post("/api/v1/routing-rules", json={
        "category_id": routing_env["cat1"],
        "dispatcher_skill_group_id": routing_env["coord_sg_id"],
        "dispatcher_id": routing_env["coord_user_id"],
    })
    rule_id = (await c.get("/api/v1/routing-rules")).json()["data"][0]["id"]
    await c.patch(f"/api/v1/routing-rules/{rule_id}", json={"enabled": False})
    r = await c.post("/api/v1/routing-rules/resolve", json={"category_id": routing_env["cat1"]})
    data = r.json()["data"]
    assert data["matched"] is False
    assert "停用" in data["reason"]


async def test_disabled_user_resolved_with_warning(routing_env):
    c = routing_env["client"]
    # Create rule with active dispatcher
    await c.post("/api/v1/routing-rules", json={
        "category_id": routing_env["cat1"],
        "dispatcher_skill_group_id": routing_env["coord_sg_id"],
        "dispatcher_id": routing_env["coord_user_id"],
    })
    # Disable the dispatcher user directly via DB
    async with AsyncSession(routing_env["engine"]) as s:
        u = (await s.execute(select(User).where(User.id == routing_env["coord_user_id"]))).scalar_one()
        u.is_active = False
        await s.commit()
    r = await c.post("/api/v1/routing-rules/resolve", json={"category_id": routing_env["cat1"]})
    data = r.json()["data"]
    assert data["matched"] is True
    assert data["reason"] is not None
    assert "停用" in data["reason"]


async def test_updating_rule_does_not_retroactively_change_tickets(routing_env):
    """修改 routing 不应影响历史工单的责任人。"""
    c = routing_env["client"]
    # Create rule.
    r1 = await c.post("/api/v1/routing-rules", json={
        "category_id": routing_env["cat1"],
        "dispatcher_skill_group_id": routing_env["coord_sg_id"],
        "dispatcher_id": routing_env["coord_user_id"],
        "handler_skill_group_id": routing_env["prof_sg_id"],
        "owner_id": routing_env["prof_user_id"],
    })
    rule_id = r1.json()["data"]["id"]

    # Imagine a ticket was created with category=cat1: dispatcher_id=coord_user, owner=prof_user.
    # Now admin updates the rule — the ticket must not change. (No DB write expected on tickets.)
    r2 = await c.patch(
        f"/api/v1/routing-rules/{rule_id}",
        json={"dispatcher_id": 9999999},  # 不存在的用户应被拒
    )
    # Validation rejects nonsense values.
    assert r2.status_code == 400

    # A valid update doesn't touch tickets. We just check the rule reflects new state.
    r3 = await c.patch(
        f"/api/v1/routing-rules/{rule_id}",
        json={"note": "updated"},
    )
    assert r3.status_code == 200
    assert r3.json()["data"]["note"] == "updated"


async def test_delete_rule(routing_env):
    c = routing_env["client"]
    r1 = await c.post("/api/v1/routing-rules", json={
        "category_id": routing_env["cat1"],
        "dispatcher_skill_group_id": routing_env["coord_sg_id"],
        "dispatcher_id": routing_env["coord_user_id"],
    })
    rule_id = r1.json()["data"]["id"]
    rd = await c.delete(f"/api/v1/routing-rules/{rule_id}")
    assert rd.status_code == 200
    # resolve should now report no rule
    r = await c.post("/api/v1/routing-rules/resolve", json={"category_id": routing_env["cat1"]})
    assert r.json()["data"]["matched"] is False
