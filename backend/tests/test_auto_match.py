"""Phase 5 tests: auto-match responsibility from routing rule on ticket create.

Verify that when a ticket is created with a category that has a routing rule:
- skill_group_id, handler_skill_group_id, dispatcher_id auto-fill from rule
- caller-provided values WIN over rule defaults
- warning is reported when no rule configured
- warning is reported when rule's dispatcher user is disabled
- owner_id is NOT auto-assigned at create time (dispatcher must approve)
"""

import pytest
import pytest_asyncio
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.category import TicketCategory
from app.models.group import SkillGroup, UserSkillGroup
from app.models.routing import CategoryRoutingRule
from app.models.user import User


# ── Fixtures ─────────────────────────────────────────────────


async def _seed_automatch_env(engine):
    """Build: skill_groups + users + a category with full routing rule."""
    now = datetime.now(timezone.utc)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        # Clean up any prior rule from earlier fixtures.
        await s.execute(CategoryRoutingRule.__table__.delete())
        await s.execute(UserSkillGroup.__table__.delete())

        admin = (await s.execute(select(User).where(User.username == "am_admin"))).scalar_one_or_none()
        if not admin:
            admin = User(username="am_admin", name="AM管理员", password_hash="x", role="admin")
            s.add(admin)
            await s.flush()

        coord_sg = (await s.execute(select(SkillGroup).where(SkillGroup.name == "am协调部"))).scalar_one_or_none()
        if not coord_sg:
            coord_sg = SkillGroup(name="am协调部", created_at=now, updated_at=now)
            s.add(coord_sg)
            await s.flush()
        prof_sg = (await s.execute(select(SkillGroup).where(SkillGroup.name == "am专业部"))).scalar_one_or_none()
        if not prof_sg:
            prof_sg = SkillGroup(name="am专业部", created_at=now, updated_at=now)
            s.add(prof_sg)
            await s.flush()
        coord_user = (await s.execute(select(User).where(User.username == "am_coord"))).scalar_one_or_none()
        if not coord_user:
            coord_user = User(username="am_coord", name="协调人甲", password_hash="x", role="agent", is_active=True)
            s.add(coord_user)
            await s.flush()
        prof_user = (await s.execute(select(User).where(User.username == "am_prof"))).scalar_one_or_none()
        if not prof_user:
            prof_user = User(username="am_prof", name="专业人乙", password_hash="x", role="agent", is_active=True)
            s.add(prof_user)
            await s.flush()

        # Link users to skill_groups
        for uid, sgid, is_d in [
            (coord_user.id, coord_sg.id, True),
            (prof_user.id, prof_sg.id, False),
        ]:
            exists = (await s.execute(
                select(UserSkillGroup).where(
                    UserSkillGroup.user_id == uid,
                    UserSkillGroup.skill_group_id == sgid,
                )
            )).scalar_one_or_none()
            if not exists:
                s.add(UserSkillGroup(user_id=uid, skill_group_id=sgid, is_dispatcher=is_d))

        # Two categories: one with rule, one without.
        cat_with = (await s.execute(select(TicketCategory).where(TicketCategory.id == 8001))).scalar_one_or_none()
        if not cat_with:
            cat_with = TicketCategory(
                id=8001, parent_id=None, name="已配置分类", level=1,
                sort_order=0, is_active=True, created_at=now, updated_at=now,
            )
            s.add(cat_with)
            await s.flush()
        cat_no = (await s.execute(select(TicketCategory).where(TicketCategory.id == 8002))).scalar_one_or_none()
        if not cat_no:
            cat_no = TicketCategory(
                id=8002, parent_id=None, name="未配置分类", level=1,
                sort_order=1, is_active=True, created_at=now, updated_at=now,
            )
            s.add(cat_no)
            await s.flush()

        # Create routing rule for cat_with
        rule = (await s.execute(
            select(CategoryRoutingRule).where(CategoryRoutingRule.category_id == 8001)
        )).scalar_one_or_none()
        if not rule:
            rule = CategoryRoutingRule(
                category_id=8001,
                dispatcher_skill_group_id=coord_sg.id,
                dispatcher_id=coord_user.id,
                handler_skill_group_id=prof_sg.id,
                owner_id=prof_user.id,
                enabled=True,
                note="automatch test",
            )
            s.add(rule)
        else:
            rule.dispatcher_skill_group_id = coord_sg.id
            rule.dispatcher_id = coord_user.id
            rule.handler_skill_group_id = prof_sg.id
            rule.owner_id = prof_user.id
            rule.enabled = True
        await s.commit()

        return {
            "admin_id": admin.id,
            "coord_sg_id": coord_sg.id,
            "prof_sg_id": prof_sg.id,
            "coord_user_id": coord_user.id,
            "prof_user_id": prof_user.id,
            "cat_with": 8001,
            "cat_no": 8002,
        }


@pytest_asyncio.fixture
async def am_env(client):
    c, _dispatcher_id, engine = client
    ids = await _seed_automatch_env(engine)
    yield {**ids, "client": c, "engine": engine}


# ── Tests ────────────────────────────────────────────────────


async def test_create_autofills_skill_group_handler_skill_group_dispatcher(am_env):
    c = am_env["client"]
    resp = await c.post("/api/v1/tickets", json={
        "description": "automatch test",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900001001",
        "category_id": am_env["cat_with"],
        # NO skill_group_id / handler_skill_group_id / dispatcher_id
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["skill_group_id"] == am_env["coord_sg_id"]
    assert data["handler_skill_group_id"] == am_env["prof_sg_id"]
    assert data["dispatcher_id"] == am_env["coord_user_id"]
    # owner_id is NOT auto-assigned (still pending state).
    assert data["owner_id"] is None


async def test_caller_provided_values_win_over_rule(am_env):
    """客服手填字段优先于路由规则。"""
    c = am_env["client"]
    # Pre-create a different coord user + sg to demonstrate override.
    factory = async_sessionmaker(am_env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        now = datetime.now(timezone.utc)
        # Different sg + user that the caller wants to use
        alt_sg = (await s.execute(select(SkillGroup).where(SkillGroup.name == "am替代部"))).scalar_one_or_none()
        if not alt_sg:
            alt_sg = SkillGroup(name="am替代部", created_at=now, updated_at=now)
            s.add(alt_sg)
            await s.flush()
        alt_user = (await s.execute(select(User).where(User.username == "am_alt_coord"))).scalar_one_or_none()
        if not alt_user:
            alt_user = User(username="am_alt_coord", name="替代协调人", password_hash="x", role="agent")
            s.add(alt_user)
            await s.flush()
        # Mark alt_user as dispatcher in alt_sg.
        exists = (await s.execute(
            select(UserSkillGroup).where(
                UserSkillGroup.user_id == alt_user.id,
                UserSkillGroup.skill_group_id == alt_sg.id,
            )
        )).scalar_one_or_none()
        if not exists:
            s.add(UserSkillGroup(user_id=alt_user.id, skill_group_id=alt_sg.id, is_dispatcher=True))
        await s.commit()
        alt_sg_id, alt_user_id = alt_sg.id, alt_user.id

    resp = await c.post("/api/v1/tickets", json={
        "description": "override",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900001002",
        "category_id": am_env["cat_with"],
        "skill_group_id": alt_sg_id,
        "dispatcher_id": alt_user_id,
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["skill_group_id"] == alt_sg_id
    assert data["dispatcher_id"] == alt_user_id
    # handler_skill_group_id still filled by rule since caller didn't set it.
    assert data["handler_skill_group_id"] == am_env["prof_sg_id"]


async def test_no_rule_category_works_with_explicit_values(am_env):
    c = am_env["client"]
    resp = await c.post("/api/v1/tickets", json={
        "description": "no rule",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900001003",
        "category_id": am_env["cat_no"],
        "skill_group_id": am_env["coord_sg_id"],
        "dispatcher_id": am_env["coord_user_id"],
    })
    assert resp.status_code == 201, resp.text
    data = resp.json()["data"]
    assert data["skill_group_id"] == am_env["coord_sg_id"]
    assert data["dispatcher_id"] == am_env["coord_user_id"]
    # No rule, so handler_skill_group_id stays null
    assert data["handler_skill_group_id"] is None


async def test_auto_match_warning_when_rule_dispatcher_disabled(am_env):
    c = am_env["client"]
    # Disable the coordinator user
    factory = async_sessionmaker(am_env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        u = (await s.execute(select(User).where(User.id == am_env["coord_user_id"]))).scalar_one()
        u.is_active = False
        await s.commit()
    resp = await c.post("/api/v1/tickets", json={
        "description": "disabled coord",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900001004",
        "category_id": am_env["cat_with"],
    })
    assert resp.status_code == 201, resp.text
    # 仍然匹配到规则 + 警告
    data = resp.json()["data"]
    assert data["dispatcher_id"] == am_env["coord_user_id"]
    assert resp.json()["warnings"] is not None
    assert "停用" in resp.json()["warnings"]["auto_match_warning"]


async def test_auto_match_warning_when_no_rule(am_env):
    c = am_env["client"]
    resp = await c.post("/api/v1/tickets", json={
        "description": "no rule",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": "13900001005",
        "category_id": am_env["cat_no"],
        "skill_group_id": am_env["coord_sg_id"],
        "dispatcher_id": am_env["coord_user_id"],
    })
    assert resp.status_code == 201, resp.text
    assert resp.json()["warnings"] is not None
    assert "尚未配置" in resp.json()["warnings"]["auto_match_warning"]