"""建单分类及即时咨询拒绝创建的回归测试。"""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from test_v2_categories import _reseed_v2
from test_workflow_regression import _next_phone

# 客服建单可选的判断终点（设计表A 判断级=客服 的行）
CS_SELECTABLE = {
    1202, 1203, 1204,      # 品牌合作 / 产品使用 / 渠道代理
    2102, 2103, 2104,      # 一般 / 重要 / 重大投诉
    2203, 2204,            # 套餐变更 / 业财对账
    2301,                  # 业务保障（售后在此分诊，二级留空）
}
# 容器节点与分诊侧节点都不可选
CS_NOT_SELECTABLE = {1001, 2101, 2201, 2302, 2310, 2311, 2312, 2313, 2321, 2322}


def _flatten(nodes, out=None):
    out = [] if out is None else out
    for n in nodes:
        out.append(n)
        _flatten(n["children"], out)
    return out


@pytest.fixture
async def cats_env(client):
    c, disp_id, engine = client
    await _reseed_v2(engine)
    # 正式建单必填对接部门/对接人：测试库没跑 seed，手动补一个部门；
    # 链配置也从 seed 常量导入（可选标注/通道判定依赖链存在）
    from app.models.dispatch import DispatchChain
    from app.models.group import SkillGroup, UserSkillGroup
    from scripts.seed import DISPATCH_CHAINS

    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        sg = SkillGroup(name="建单测试部门")
        s.add(sg)
        await s.flush()
        s.add(UserSkillGroup(user_id=disp_id, skill_group_id=sg.id, is_dispatcher=True))
        for cid, depts, note in DISPATCH_CHAINS:
            s.add(DispatchChain(
                category_id=cid,
                steps=[{"order": i + 1, "department_code": d} for i, d in enumerate(depts)],
                note=note,
            ))
        await s.commit()
        await s.refresh(sg)
    yield {"client": c, "engine": engine, "dispatcher_id": disp_id, "sg_id": sg.id}


async def test_categories_create_selectable_flags(cats_env):
    c = cats_env["client"]
    resp = await c.get("/api/v1/categories")
    assert resp.status_code == 200
    flat = _flatten(resp.json()["data"])
    by_id = {n["id"]: n for n in flat}

    selectable = {n["id"] for n in flat if n.get("create_selectable")}
    assert selectable == CS_SELECTABLE

    for cid in CS_NOT_SELECTABLE:
        assert not by_id[cid]["create_selectable"], f"{cid} 不应出现在建单表单"

    # 通道标注
    assert 2202 not in by_id
    assert by_id[2301]["channel"] == "chain"
    assert by_id[2302]["channel"] == "chain"      # 可路由（分诊落位用），但不可建单选
    assert by_id[2103]["channel"] == "manual"     # 重要投诉走升级策略，人工分派


async def _create(c, category_id, **extra):
    payload = dict(
        description="channel test",
        priority="p4_enterprise",
        channel="phone",
        customer_type="personal",
        customer_phone=_next_phone(),
        category_id=category_id,
    )
    payload.update(extra)
    resp = await c.post("/api/v1/tickets", json=payload)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_removed_package_query_cannot_create_ticket(cats_env):
    resp = await cats_env["client"].post("/api/v1/tickets", json={
        "description": "套餐查询不应记录工单",
        "priority": "p4_enterprise",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": _next_phone(),
        "category_id": 2202,
    })
    assert resp.status_code == 422


async def test_removed_instant_consult_cannot_create_ticket(cats_env):
    resp = await cats_env["client"].post("/api/v1/tickets", json={
        "description": "旧即时咨询分类不应继续建单",
        "priority": "p4_enterprise",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": _next_phone(),
        "category_id": 1102,
    })
    assert resp.status_code == 422


async def test_normal_category_unaffected(cats_env):
    """业务保障等正常分类仍走 pending 等分派（不被即办结预置劫持）。"""
    j = await _create(
        cats_env["client"], 2301,
        skill_group_id=cats_env["sg_id"],
        dispatcher_id=cats_env["dispatcher_id"],
    )
    d = j["data"]
    assert d["state"] == "pending"
    assert d["resolved"] is False
