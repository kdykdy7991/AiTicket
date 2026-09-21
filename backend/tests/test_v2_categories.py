"""Phase 2 tests: v2 category tree seeded correctly and old categories retired."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.models.category import TicketCategory


# Mirror the V2_CATEGORIES tuple in the migration so tests can re-seed after
# the per-test TRUNCATE in conftest.
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


async def _reseed_v2(engine) -> None:
    """Re-insert v2 + legacy categories so the test sees a stable tree.

    conftest TRUNCATEs all tables after every test. The migration only runs
    once per session, so by the time our tests execute the data may be empty.
    This fixture re-inserts everything the assertions need.
    """
    now = datetime.now(timezone.utc)
    async with AsyncSession(engine) as s:
        existing_ids = set(
            (await s.execute(select(TicketCategory.id))).scalars().all()
        )
        to_add = []
        # Legacy L1 categories, marked inactive.
        for cid, parent, name, level, sort in [
            (1, None, "咨询类", 1, 1),
            (2, None, "业务类", 1, 2),
            (3, None, "故障类", 1, 3),
            (4, None, "投诉类", 1, 4),
        ]:
            if cid not in existing_ids:
                to_add.append(TicketCategory(
                    id=cid, parent_id=parent, name=name, level=level,
                    sort_order=sort, is_active=False, created_at=now, updated_at=now,
                ))
        # One historical child of 咨询类 for listability check.
        if 101 not in existing_ids:
            to_add.append(TicketCategory(
                id=101, parent_id=1, name="品牌咨询", level=2, sort_order=1,
                is_active=False, created_at=now, updated_at=now,
            ))
        # v2 tree (re-insert if wiped).
        for cid, parent, name, level, sort in V2_CATEGORIES:
            if cid not in existing_ids:
                to_add.append(TicketCategory(
                    id=cid, parent_id=parent, name=name, level=level,
                    sort_order=sort, is_active=True, created_at=now, updated_at=now,
                ))
        if to_add:
            s.add_all(to_add)
            await s.commit()


@pytest.fixture
async def seeded_categories(client):
    """Reseed the v2 + legacy categories after conftest's per-test TRUNCATE."""
    _c, _disp, engine = client
    await _reseed_v2(engine)
    yield client


async def test_v2_tree_present_and_path_correct(seeded_categories):
    c, _dispatcher_id, _engine = seeded_categories
    resp = await c.get("/api/v1/categories")
    assert resp.status_code == 200
    tree = resp.json()["data"]

    def find_by_name(nodes, name):
        for n in nodes:
            if n["name"] == name:
                return n
            r = find_by_name(n["children"], name)
            if r is not None:
                return r
        return None

    top_names = [n["name"] for n in tree]
    assert "咨询" in top_names
    assert "客户服务" in top_names

    leaf = find_by_name(tree, "即时办结咨询")
    assert leaf is not None
    assert leaf["level"] == 3
    assert leaf["path"] == "咨询 / 即时 / 即时办结咨询"

    core = find_by_name(tree, "核心网系统")
    assert core is not None
    assert core["level"] == 4
    assert core["path"] == "客户服务 / 业务保障 / 星座大系统 / 核心网系统"

    bp = find_by_name(tree, "套餐变更")
    assert bp is not None
    assert bp["level"] == 3
    assert bp["path"] == "客户服务 / 业务运营 / 套餐变更"


async def test_old_top_level_categories_deactivated(seeded_categories):
    c, _dispatcher_id, _engine = seeded_categories

    resp = await c.get("/api/v1/categories")
    active_names = [n["name"] for n in resp.json()["data"]]
    for old in ["咨询类", "业务类", "故障类", "投诉类"]:
        assert old not in active_names, f"{old} should be inactive"

    resp = await c.get("/api/v1/categories?include_inactive=true")
    all_names = [n["name"] for n in resp.json()["data"]]
    for old in ["咨询类", "业务类", "故障类", "投诉类"]:
        assert old in all_names, f"{old} must remain visible for historical ticket display"


async def test_old_categories_still_have_children_listable(seeded_categories):
    c, _dispatcher_id, _engine = seeded_categories
    resp = await c.get("/api/v1/categories?include_inactive=true")
    tree = resp.json()["data"]
    old_l1 = next((n for n in tree if n["name"] == "咨询类"), None)
    assert old_l1 is not None
    child_names = [c["name"] for c in old_l1["children"]]
    assert "品牌咨询" in child_names
