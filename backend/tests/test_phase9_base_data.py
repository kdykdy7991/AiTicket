"""Phase 9 tests: v2 base data (skill_groups + users + category_routing_rules).

This test imports scripts/seed.py and runs seed_phase9_base_data() against the
test DB. The categories are already created by Phase 2 migration.

We verify:
- New skill_groups seeded (100-106)
- New users seeded (200-214)
- User_skill_groups links seeded
- Category_routing_rules created for each v2 leaf category
- The data is idempotent: running twice doesn't break
"""

import asyncio
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.category import TicketCategory
from app.models.group import SkillGroup, UserSkillGroup
from app.models.routing import CategoryRoutingRule
from app.models.user import User


def _run_seed_phase9():
    """Run scripts/seed.py --phase9 as a subprocess against the test DB."""
    env = {"DATABASE_URL": "postgresql+asyncpg://skdy:skdy123@localhost:5433/skdy_ticket_test",
           "PATH": "/usr/bin:/bin"}
    import os
    full_env = {**os.environ, **env}
    result = subprocess.run(
        [sys.executable, "scripts/seed.py", "--phase9"],
        cwd=Path(__file__).resolve().parents[1],
        env=full_env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result


async def _seed_phase9_directly(engine):
    """In-process equivalent of seed.py --phase9 for fast tests.

    Reimports the seed module in-process with the test engine so we don't have
    to share the global session/connection state.
    """
    import importlib
    import os
    os.environ["DATABASE_URL"] = "postgresql+asyncpg://skdy:skdy123@localhost:5433/skdy_ticket_test"
    # Re-import seed module fresh (its module-level `engine`/`async_session`
    # are bound to whatever DATABASE_URL was at import time).
    if "scripts.seed" in sys.modules:
        del sys.modules["scripts.seed"]
    seed_mod = importlib.import_module("scripts.seed")
    # Override the engine / session to point at the test DB.
    seed_mod.engine = engine
    seed_mod.async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    await seed_mod.seed_phase9_base_data()


async def _category_exists(engine, cat_id: int) -> bool:
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        r = await s.execute(select(TicketCategory.id).where(TicketCategory.id == cat_id))
        return r.scalar_one_or_none() is not None


async def _ensure_v2_categories(engine):
    """Re-seed v2 categories after per-test TRUNCATE (idempotent via ON CONFLICT)."""
    from scripts.seed import V2_CAT
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        if await _category_exists(engine, V2_CAT["即时办结咨询"]):
            return
        # Inline the v2 categories (mirrors f2a3b4c5d6e7)
        # (id, parent_id, name, level, sort_order)
        V2_CATEGORIES = [
            (1001, None, "咨询", 1, 1),
            (1002, None, "客户服务", 1, 2),
            (1101, 1001, "即时", 2, 1),
            (1102, 1101, "即时办结咨询", 3, 1),
            (1201, 1001, "非即时", 2, 1),
            (1202, 1201, "品牌合作", 3, 1),
            (1203, 1201, "产品使用/参数咨询", 3, 2),
            (1204, 1201, "渠道/代理合作", 3, 3),
            (2101, 1002, "服务投诉", 2, 1),
            (2102, 2101, "一般投诉", 3, 1),
            (2103, 2101, "重要投诉", 3, 2),
            (2104, 2101, "重大投诉", 3, 3),
            (2201, 1002, "业务运营", 2, 1),
            (2202, 2201, "套餐查询", 3, 1),
            (2203, 2201, "套餐变更", 3, 2),
            (2204, 2201, "业财对账", 3, 3),
            (2301, 1002, "业务保障", 2, 1),
            (2302, 2301, "应用平台", 3, 1),
            (2310, 2301, "星座大系统", 3, 2),
            (2311, 2310, "核心网系统", 4, 1),
            (2312, 2310, "测运控系统", 4, 2),
            (2313, 2310, "卫星系统", 4, 3),
            (2321, 2301, "终端软件", 3, 3),
            (2322, 2301, "硬件故障", 3, 4),
        ]
        now = datetime.now(timezone.utc)
        for cid, parent, name, level, sort in V2_CATEGORIES:
            existing = await s.execute(
                select(TicketCategory).where(TicketCategory.id == cid)
            )
            if existing.scalar_one_or_none():
                continue
            s.add(TicketCategory(
                id=cid, parent_id=parent, name=name, level=level,
                sort_order=sort, is_active=True, created_at=now, updated_at=now,
            ))
        await s.commit()


@pytest_asyncio.fixture
async def phase9_env(client):
    _, _, engine = client
    await _ensure_v2_categories(engine)
    return {"client": client[0], "engine": engine}


async def test_phase9_seed_creates_v2_skill_groups(phase9_env):
    """Phase 9 seed creates 7 new skill_groups (100..106)."""
    engine = phase9_env["engine"]
    await _seed_phase9_directly(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        sg_names = (await s.execute(
            select(SkillGroup.name).where(SkillGroup.id >= 100, SkillGroup.id <= 106)
        )).scalars().all()
    expected = {
        "服务投诉协调组", "业务运营组", "业务保障组",
        "核心网组", "测运控组", "卫星组", "即时办结咨询组",
    }
    assert set(sg_names) == expected


async def test_phase9_seed_creates_v2_users(phase9_env):
    engine = phase9_env["engine"]
    await _seed_phase9_directly(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        usernames = (await s.execute(
            select(User.username).where(User.id >= 200, User.id <= 214)
        )).scalars().all()
    assert "v2_dispatcher_complaint" in usernames
    assert "v2_owner_satellite" in usernames


async def test_phase9_seed_creates_routing_rules(phase9_env):
    engine = phase9_env["engine"]
    await _seed_phase9_directly(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        rules = (await s.execute(
            select(CategoryRoutingRule)
            .where(CategoryRoutingRule.category_id >= 1000)
        )).scalars().all()
    cat_ids = {r.category_id for r in rules}
    from scripts.seed import V2_CAT
    assert V2_CAT["即时办结咨询"] in cat_ids
    assert V2_CAT["核心网系统"] in cat_ids
    assert V2_CAT["卫星系统"] in cat_ids


async def test_phase9_seed_idempotent(phase9_env):
    """Running seed_phase9 twice should not error."""
    engine = phase9_env["engine"]
    await _seed_phase9_directly(engine)
    await _seed_phase9_directly(engine)

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        n_rules = len((await s.execute(
            select(CategoryRoutingRule).where(CategoryRoutingRule.category_id >= 1000)
        )).scalars().all())
    from scripts.seed import V2_ROUTING_RULES
    assert n_rules == len(V2_ROUTING_RULES)