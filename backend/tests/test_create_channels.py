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


async def test_intake_form_accepts_judgement_endpoint_and_rejects_its_child(cats_env):
    c = cats_env["client"]
    payload = {
        "intake_form": True,
        "customer_name": "王先生", "customer_company": "蓝海智联",
        "industry": "海洋渔业", "customer_phone": _next_phone(),
        "category_id": 2301, "satellite_number": "8986043100123456789",
        "is_opportunity": False,
        "description": "终端离线", "fault_occurred_at": "2026-10-15T09:30:00+08:00",
        "fault_recurrence": "偶发", "fault_location": "海边",
        "is_batch_fault": False,
        "dispatcher_id": cats_env["dispatcher_id"],
    }
    created = await c.post("/api/v1/tickets", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["data"]["category_id"] == 2301

    rejected = await c.post("/api/v1/tickets", json={**payload, "category_id": 2302})
    assert rejected.status_code == 422
    assert "继续细化" in rejected.json()["detail"]


async def test_intake_form_new_industries_and_no_expected_result(cats_env):
    for industry in ("工程机械", "智能网联", "交通物流", "能源行业", "应急通信", "智慧林草",
                     "低空出行", "智慧水利", "智慧农业", "Robotaxi", "未提供"):
        response = await cats_env["client"].post("/api/v1/tickets", json={
            "intake_form": True, "customer_name": "客户", "customer_company": "公司",
            "industry": industry, "customer_phone": _next_phone(), "category_id": 1202,
            "is_opportunity": False, "description": "合作咨询",
            "dispatcher_id": cats_env["dispatcher_id"],
        })
        assert response.status_code == 201, (industry, response.text)
        assert response.json()["data"]["expected_result"] is None


async def test_opportunity_only_requires_contact_and_core_customer_fields(cats_env):
    from app.models.group import SkillGroup, UserSkillGroup
    factory = async_sessionmaker(cats_env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        sales = SkillGroup(name="销售")
        s.add(sales)
        await s.flush()
        s.add(UserSkillGroup(user_id=cats_env["dispatcher_id"], skill_group_id=sales.id))
        await s.commit()
    payload = {
        "intake_form": True, "is_opportunity": True,
        "channel": "phone", "priority": "p4_enterprise",
        "customer_name": "客户", "customer_company": "公司", "industry": "智慧农业",
        "customer_phone": _next_phone(), "contact_phone": "13800138000",
        "description": "潜在合作需求", "sales_owner_id": cats_env["dispatcher_id"],
    }
    created = await cats_env["client"].post("/api/v1/tickets", json=payload)
    assert created.status_code == 201, created.text
    data = created.json()["data"]
    assert data["is_opportunity"] is True and data["category_id"] is None
    assert data["state"] == "open" and data["owner_id"] == cats_env["dispatcher_id"]
    assert data["dispatcher_id"] is None
    assert data["skill_group_id"] == sales.id
    assert data["expected_result"] is None
    missing = await cats_env["client"].post("/api/v1/tickets", json={**payload, "contact_phone": None})
    assert missing.status_code == 422
