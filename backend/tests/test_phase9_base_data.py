"""Phase 9 seed keeps the complaint fallback and current dispatch chains."""

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
        if await _category_exists(engine, 1202):
            return
        # Inline the v2 categories (mirrors f2a3b4c5d6e7)
        # (id, parent_id, name, level, sort_order)
        V2_CATEGORIES = [
            (1001, None, "客户咨询", 1, 1),
            (1202, 1001, "品牌合作", 2, 1),
            (1203, 1001, "产品使用/参数咨询", 2, 2),
            (1204, 1001, "渠道/代理合作", 2, 3),
            (2101, None, "服务投诉", 1, 1),
            (2102, 2101, "一般投诉", 3, 1),
            (2103, 2101, "重要投诉", 3, 2),
            (2104, 2101, "重大投诉", 3, 3),
            (2201, None, "业务运营", 1, 1),
            (2203, 2201, "套餐变更", 3, 2),
            (2204, 2201, "业财对账", 3, 3),
            (2301, None, "业务保障", 1, 1),
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
                sort_order=sort, is_active=True,
                created_at=now, updated_at=now,
            ))
        await s.commit()


@pytest_asyncio.fixture
async def phase9_env(client):
    _, _, engine = client
    await _ensure_v2_categories(engine)
    # phase9 补种依赖 legacy 1-8 skill_group (品牌传播/产品/市场生态部) 与
    # 对应 dispatcher 绑定。但 conftest 已经预先插了 admin/test-dispatcher，
    # 直接调 seed() 会因 users 非空而 early-return；这里走强制补种路径。
    await _seed_legacy_basics(engine)
    return {"client": client[0], "engine": engine}


async def _seed_legacy_basics(engine):
    """强制补种 legacy skill_groups 1-8 + 关键 dispatcher 绑定。

    复用 scripts/seed.py 顶部常量；只插 SKILL_GROUPS / GROUPS(用于
    user.group_id 外键) / USERS / USER_SKILL_GROUPS 中与本测试相关的
    部分。本测试只查 user_skill_groups 的 is_dispatcher 关系,无需登录。
    """
    from scripts.seed import (
        SKILL_GROUPS, GROUPS, USERS, USER_SKILL_GROUPS, _SKDY_HASH,
    )
    from app.models.user import User
    from app.models.group import SkillGroup, UserSkillGroup, Group
    from datetime import datetime, timezone
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as s:
        # groups 表 (id=1 客服组,users.group_id 外键依赖)
        for row in GROUPS:
            existing = (await s.execute(
                select(Group).where(Group.id == row[0])
            )).scalar_one_or_none()
            if existing is None:
                s.add(Group(id=row[0], name=row[1],
                            created_at=now, updated_at=now))
        # legacy skill_groups 1-8
        for sg in SKILL_GROUPS:
            existing = (await s.execute(
                select(SkillGroup).where(SkillGroup.id == sg[0])
            )).scalar_one_or_none()
            if existing is None:
                s.add(SkillGroup(id=sg[0], name=sg[1],
                                 created_at=now, updated_at=now))
        # 关键 dispatcher users (钟梦茜/谢志鹏/张朝娟 + 它们的归属)
        for u in USERS:
            uid = u[0]
            existing = (await s.execute(
                select(User).where(User.id == uid)
            )).scalar_one_or_none()
            if existing is None:
                s.add(User(
                    id=uid, username=u[1], name=u[2], role=u[3],
                    group_id=u[4], is_group_leader=u[5],
                    password_hash=u[6] or _SKDY_HASH,
                    is_active=True,
                    created_at=now, updated_at=now,
                ))
        for usg in USER_SKILL_GROUPS:
            existing = (await s.execute(
                select(UserSkillGroup).where(
                    UserSkillGroup.user_id == usg[0],
                    UserSkillGroup.skill_group_id == usg[1],
                )
            )).scalar_one_or_none()
            if existing is None:
                s.add(UserSkillGroup(
                    user_id=usg[0], skill_group_id=usg[1],
                    is_dispatcher=usg[2],
                ))
        await s.commit()


async def test_phase9_seed_keeps_only_required_groups(phase9_env):
    engine = phase9_env["engine"]
    await _seed_phase9_directly(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        sg_names = (await s.execute(
            select(SkillGroup.name).where(SkillGroup.id >= 100, SkillGroup.id <= 106)
        )).scalars().all()
    expected = {"服务投诉协调组", "测运控组"}
    assert set(sg_names) == expected


async def test_phase9_seed_keeps_only_complaint_placeholder(phase9_env):
    engine = phase9_env["engine"]
    await _seed_phase9_directly(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        users = (await s.execute(
            select(User).where(User.id >= 200, User.id <= 214)
        )).scalars().all()
    assert len(users) == 1
    assert users[0].username == "服务投诉协调人占位账号"
    assert users[0].role == "handler" and users[0].group_id is None
    assert users[0].local_login_enabled is True
    async with factory() as s:
        constellation_placeholder = (await s.execute(
            select(User).where(User.username == "constellation_lead")
        )).scalar_one_or_none()
    assert constellation_placeholder is None


async def test_phase9_seed_keeps_only_complaint_rule(phase9_env):
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
    assert 1102 not in cat_ids
    assert cat_ids == {V2_CAT["服务投诉"]}


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
    assert n_rules == len(V2_ROUTING_RULES) == 1


# ── Phase 9 补丁：rename + 正式链 ──────────────────────
async def test_phase9_renames_legacy_skill_groups(phase9_env):
    """Phase 9 seed 把 品牌公关传播→品牌传播与大客户、产品中心→产品。"""
    engine = phase9_env["engine"]
    await _seed_phase9_directly(engine)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        names = (await s.execute(
            select(SkillGroup.id, SkillGroup.name).where(SkillGroup.id.in_([1, 2, 3]))
        )).all()
    by_id = {row[0]: row[1] for row in names}
    assert by_id[1] == "品牌传播与大客户"
    assert by_id[2] == "市场生态部"   # 不变
    assert by_id[3] == "产品"


async def test_phase9_seed_resolves_formal_chains_and_complaint_fallback(phase9_env):
    engine = phase9_env["engine"]
    await _seed_phase9_directly(engine)
    from app.services.dispatch_chain import resolve_responsibility
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    expectations = {
        1202: "品牌传播与大客户", 1203: "产品", 1204: "市场生态部",
        2301: "售后", 2311: "软件开发组", 2312: "测运控组",
        2313: "整星产品", 2203: "市场生态部", 2204: "销售",
    }
    async with factory() as s:
        for cat_id, department in expectations.items():
            r = await resolve_responsibility(s, cat_id)
            assert r["via"] == "chain" and r["matched"] is True, r
            assert r["matched_rule_category_id"] == cat_id, r
            assert r["dispatcher_skill_group_name"] == department, r
        for cat_id in (2103, 2104):
            r = await resolve_responsibility(s, cat_id)
            assert r["via"] == "rule" and r["matched_rule_category_id"] == 2101, r
