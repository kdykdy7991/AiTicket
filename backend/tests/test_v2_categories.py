"""Current category tree, including the new immediate consultation leaf."""

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from datetime import datetime, timezone

from app.models.category import TicketCategory
from test_workflow_regression import _next_phone


# Mirror the V2_CATEGORIES tuple in the migration so tests can re-seed after
# the per-test TRUNCATE in conftest.
V2_CATEGORIES = [
    (1001, None, "客户咨询", 1, 1),
    (1202, 1001, "品牌合作", 2, 1),
    (1203, 1001, "产品使用/参数咨询", 2, 2),
    (1204, 1001, "渠道/代理合作", 2, 3),
    (1205, 1001, "即时办结咨询", 2, 4),
    (2101, None, "服务投诉", 1, 2),
    (2102, 2101, "一般投诉", 2, 1),
    (2103, 2101, "重要投诉", 2, 2),
    (2104, 2101, "重大投诉", 2, 3),
    (2201, None, "业务运营", 1, 3),
    (2203, 2201, "套餐变更", 2, 2),
    (2204, 2201, "业财对账", 2, 3),
    (2301, None, "业务保障", 1, 4),
    (2302, 2301, "应用平台", 2, 1),
    (2310, 2301, "星座大系统", 2, 2),
    (2311, 2310, "核心网系统", 3, 1),
    (2312, 2310, "测运控系统", 3, 2),
    (2313, 2310, "卫星系统", 3, 3),
    (2321, 2301, "终端软件", 2, 3),
    (2322, 2301, "硬件故障", 2, 4),
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
                    sort_order=sort, is_active=True,
                    created_at=now, updated_at=now,
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
    # 客户咨询的四个二级分类直接挂在根节点下。
    assert top_names == ["客户咨询", "服务投诉", "业务运营", "业务保障"]

    consult = find_by_name(tree, "客户咨询")
    assert consult is not None
    assert [child["name"] for child in consult["children"]] == [
        "品牌合作", "产品使用/参数咨询", "渠道/代理合作", "即时办结咨询",
    ]
    assert find_by_name(tree, "即时") is None
    assert find_by_name(tree, "即时办结咨询")["channel"] == "instant"
    assert find_by_name(tree, "非即时") is None

    core = find_by_name(tree, "核心网系统")
    assert core is not None
    assert core["level"] == 3
    assert core["path"] == "业务保障 / 星座大系统 / 核心网系统"

    bp = find_by_name(tree, "套餐变更")
    assert bp is not None
    assert bp["level"] == 2
    assert bp["path"] == "业务运营 / 套餐变更"


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


async def test_lineage_index_resolves_l1_l2_and_path(seeded_categories):
    """血缘索引：L1=根节点、L2=根的直接子级、path=root→leaf 全链。

    回归 4 层树：旧实现 `t.category.parent.name` 只取一层 parent，会把
    二级节点「业务保障」当成一级，或把 L3「星座大系统」当成一级。
    """
    from app.services.category_utils import build_lineage_index

    _c, _dispatcher_id, engine = seeded_categories
    async with AsyncSession(engine) as s:
        index = await build_lineage_index(s)

    def names(cid):
        return [c.name for c in index[cid].path]

    # L3叶子：业务保障 / 星座大系统 / 核心网系统
    lin = index[2311]
    assert lin.l1.name == "业务保障"
    assert lin.l2.name == "星座大系统"
    assert names(2311) == ["业务保障", "星座大系统", "核心网系统"]

    # 客户咨询直接挂三个二级分类
    assert index[1202].l1.name == "客户咨询"
    assert index[1202].l2.name == "品牌合作"
    assert names(1202) == ["客户咨询", "品牌合作"]

    # L2 自身：没有更深层，L2 就是自己
    # 业务保障提为一级后没有 L2
    assert index[2301].l1.name == "业务保障"
    assert index[2301].l2 is None
    assert names(2301) == ["业务保障"]

    # L1 自身：无 L2
    assert index[2101].l1.name == "服务投诉"
    assert index[2101].l2 is None
    assert names(2101) == ["服务投诉"]

    # 旧的 2 层扁平树（历史工单）行为不变
    assert index[101].l1.name == "咨询类"
    assert index[101].l2.name == "品牌咨询"
    assert names(101) == ["咨询类", "品牌咨询"]


async def test_ticket_detail_exposes_correct_l1_l2_path(seeded_categories):
    """端到端：工单详情的 category_l1/l2/path 走血缘派生。"""
    from app.models.dispatch import DispatchChain
    from app.models.group import SkillGroup, UserSkillGroup
    from app.services.category_utils import build_lineage_index
    from scripts.seed import DISPATCH_CHAINS, dispatch_chain_steps

    c, disp_id, engine = seeded_categories
    # 正式建单必填对接部门/对接人；链配置决定落位，测试库没跑 seed 故手动补
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        sg = SkillGroup(name="血缘测试部门")
        s.add(sg)
        await s.flush()
        s.add(UserSkillGroup(user_id=disp_id, skill_group_id=sg.id, is_dispatcher=True))
        for cid, depts, note in DISPATCH_CHAINS:
            s.add(DispatchChain(
                category_id=cid,
                steps=dispatch_chain_steps(cid, depts),
                note=note,
            ))
        await s.commit()
        await s.refresh(sg)
        dispatcher_id, sg_id = disp_id, sg.id

    # 2301 业务保障是客服建单可选的判断终点（L2），L1 应为「客户服务」
    resp = await c.post("/api/v1/tickets", json={
        "description": "分类血缘回归测试",
        "priority": "p4_enterprise",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": _next_phone(),
        "category_id": 2301,
        "skill_group_id": sg_id,
        "dispatcher_id": dispatcher_id,
    })
    assert resp.status_code == 201, resp.text
    d = resp.json()["data"]
    assert d["category_l1_name"] == "业务保障"
    assert d["category_l2_name"] is None
    assert d["category_name"] == "业务保障"
    assert d["category_path"] == "业务保障"

    # 分诊细化后路径加深；业务保障已是 L1，故 L1/L2 分别为业务保障/星座大系统
    async with factory() as s:
        index = await build_lineage_index(s)
    assert "星座大系统" in [c.name for c in index[2310].path]
    assert index[2310].l1.name == "业务保障"
    assert index[2310].l2.name == "星座大系统"


async def test_responsibility_slots_judgement_vs_handling(seeded_categories):
    """责任槽位推导：判断组沿分类父链上溯，处理部门只取叶子自己的链首。

    业务前提：客服建单时确认一/二级分类后，该分类是否需要后续继续判断、
    由谁判断，是分类的静态属性（记录在 dispatch_chains），不是运行时历史。
    """
    from app.models.dispatch import DispatchChain
    from app.services.category_utils import build_responsibility_index
    from scripts.seed import DISPATCH_CHAINS, dispatch_chain_steps

    _c, _dispatcher_id, engine = seeded_categories
    # conftest 每次 TRUNCATE，dispatch_chains 需重灌（分类已由 seeded_categories 灌好）
    async with AsyncSession(engine) as s:
        for cid, depts, note in DISPATCH_CHAINS:
            s.add(DispatchChain(
                category_id=cid,
                steps=dispatch_chain_steps(cid, depts),
                note=note,
            ))
        await s.commit()

    async with AsyncSession(engine) as s:
        idx = await build_responsibility_index(s)

    def slots(cid):
        return idx[cid]

    # 叶子分类：链首部门=处理部门，祖先链首=判断组（判断先后=根→叶）
    core = slots(2311)  # 核心网系统：业务保障/星座大系统/核心网系统
    assert core.judgement_departments == ("售后", "星座大系统负责人")
    assert core.transit_departments == ()
    assert core.handling_department == "软件开发组"

    # 判断节点分类（有启用子节点）：链首仍需继续分诊 → 计入判断组，处理部门待定
    assure = slots(2301)  # 业务保障，客服判到此级，售后在此分诊
    assert assure.judgement_departments == ("售后",)
    assert assure.transit_departments == ()
    assert assure.handling_department is None

    sats = slots(2310)  # 星座大系统：售后分诊到此，负责人再判断
    assert sats.judgement_departments == ("售后", "星座大系统负责人")
    assert sats.transit_departments == ()
    assert sats.handling_department is None

    # 单步直达且父链无链：客服组建单时已判断完 → 判断组为空
    brand = slots(1202)  # 品牌合作
    assert brand.judgement_departments == ()
    assert brand.transit_departments == ()
    assert brand.handling_department == "品牌传播与大客户"

    # 跨分支：客户咨询/非即时/品牌合作，判断组为空
    assert slots(1202).judgement_departments == ()
    # 祖先链存在但本人是叶子：判断组=祖先
    consult = slots(1203)  # 产品使用/参数咨询（父 1201 无链）
    assert consult.judgement_departments == ()
    assert consult.handling_department == "产品"

    # 判断方=处理方的场景（硬件故障 note 明确说明）
    hw = slots(2322)
    assert hw.handling_department == "售后"
    assert hw.transit_departments == ()

    # 多步链（审核→执行）：中间环节=流转节点，最后一环=处理部门
    change = slots(2203)  # 套餐变更：[市场生态部, 业务支撑组]
    assert change.judgement_departments == ()
    assert change.transit_departments == ("市场生态部",)
    assert change.handling_department == "业务支撑组"

    ledger = slots(2204)  # 业财对账：[经营管理部, 财务]
    assert ledger.transit_departments == ("经营管理部",)
    assert ledger.handling_department == "财务"
