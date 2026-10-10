"""V0.21 分诊（refine）：能力位、直下级校验、链重算与接续规则。

覆盖设计 §2（三级判断/分诊细化一级）与 §4（接续规则）：
- 建单写入链快照；
- 分诊换部门（open 换 owner）/ 接续规则（判断方=处理方则原地不动）；
- 非直下级 400、末级 403、非判断人 403。
"""

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.main import app
from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.ticket import TicketStateLog
from app.models.user import User

from test_workflow_regression import _next_phone, action_sequence, as_user

# 只插入用到的分类：2301 业务保障（L2）与其子级
CATS = [
    (2301, None, "业务保障", 1, 1),
    (2302, 2301, "应用平台", 3, 1),
    (2310, 2301, "星座大系统", 3, 2),
    (2311, 2310, "核心网系统", 4, 1),
    (2322, 2301, "硬件故障", 3, 4),
]

# 表A 链：2301/2322 → 售后；2302 → 平台运维组
CHAINS = [
    (2301, [{"order": 1, "department_code": "售后"}]),
    (2302, [{"order": 1, "department_code": "平台运维组"}]),
    (2322, [{"order": 1, "department_code": "售后"}]),
]


@pytest_asyncio.fixture
async def renv(client):
    """分类树 + 两条部门链 + 各一名对接人（表B）。"""
    c, _dispatcher_id, engine = client
    now = datetime.now(timezone.utc)
    factory = async_sessionmaker_for(engine)
    async with factory() as s:
        # migration 已种过 v2 分类树（首个测试时表非空），只补缺失行
        existing = set((await s.execute(select(TicketCategory.id))).scalars().all())
        for cid, parent, name, level, sort in CATS:
            if cid not in existing:
                s.add(TicketCategory(
                    id=cid, parent_id=parent, name=name, level=level,
                    sort_order=sort, is_active=True, created_at=now, updated_at=now,
                ))
        sgs = {
            sg.name: sg
            for sg in (await s.execute(
                select(SkillGroup).where(SkillGroup.name.in_(["售后", "平台运维组"]))
            )).scalars()
        }
        sg_aftersale = sgs.get("售后") or SkillGroup(name="售后")
        sg_platform = sgs.get("平台运维组") or SkillGroup(name="平台运维组")
        s.add_all([sg for sg in (sg_aftersale, sg_platform) if sg.id is None])
        await s.flush()
        u_as = User(username="rf-aftersale", name="售后对接", password_hash="x", role="handler")
        u_pl = User(username="rf-platform", name="平台对接", password_hash="x", role="handler")
        s.add_all([u_as, u_pl])
        await s.flush()
        s.add_all([
            UserSkillGroup(user_id=u_as.id, skill_group_id=sg_aftersale.id, is_dispatcher=True),
            UserSkillGroup(user_id=u_pl.id, skill_group_id=sg_platform.id, is_dispatcher=True),
        ])
        s.add_all([
            DispatchChain(category_id=cid, steps=steps) for cid, steps in CHAINS
        ])
        await s.commit()
        ids = {
            "aftersale_user": u_as.id,
            "platform_user": u_pl.id,
            "sg_aftersale": sg_aftersale.id,
            "sg_platform": sg_platform.id,
        }

    async def create_ticket(**kw):
        payload = dict(
            description="refine test",
            priority="p3_normal",
            channel="phone",
            customer_type="personal",
            customer_phone=_next_phone(),
            category_id=2301,
        )
        payload.update(kw)
        r = await c.post("/api/v1/tickets", json=payload)
        assert r.status_code == 201, r.text
        return r.json()["data"]

    async def refine(tid, category_id, expect=200):
        r = await c.post(f"/api/v1/tickets/{tid}/refine", json={"category_id": category_id})
        assert r.status_code == expect, r.text
        return r.json()["data"] if expect == 200 else r

    async def patch(tid, payload, expect=200):
        r = await c.patch(f"/api/v1/tickets/{tid}", json=payload)
        assert r.status_code == expect, r.text
        return r.json() if expect == 200 else r

    yield {
        "client": c, "engine": engine,
        "create_ticket": create_ticket, "refine": refine, "patch": patch,
        **ids,
    }


def async_sessionmaker_for(engine):
    from sqlalchemy.ext.asyncio import async_sessionmaker
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def test_create_writes_chain_snapshot(renv):
    """建单即落链快照（链优先预填部门/对接人）。"""
    t = await renv["create_ticket"]()
    assert t["dispatch_chain_steps"] == [{"order": 1, "department_code": "售后"}]
    assert t["dispatch_step_index"] == 0
    assert t["skill_group_name"] == "售后"
    assert t["dispatcher_id"] == renv["aftersale_user"]


async def test_business_assurance_goes_directly_to_judgement(renv):
    t = await renv["create_ticket"](
        skill_group_id=renv["sg_platform"],
        dispatcher_id=renv["platform_user"],
    )
    assert t["skill_group_name"] == "售后"
    assert t["dispatcher_id"] == renv["aftersale_user"]
    detail = (await renv["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    assert detail["can_refine"] is True
    assert not any(a["action"] == "dispatch" for a in detail["allowed_actions"])
    await renv["patch"](
        t["id"], {"state": "open", "owner_id": renv["aftersale_user"]}, expect=403
    )


async def test_refine_switches_chain_and_dept(renv):
    """pending 分诊：分类/链/部门切到子级，状态不变，留下 refine 自环日志。"""
    t = await renv["create_ticket"]()
    d = await renv["refine"](t["id"], 2302)

    assert d["state"] == "pending"
    assert d["category_id"] == 2302
    assert d["skill_group_name"] == "平台运维组"
    assert d["dispatcher_id"] == renv["platform_user"]
    assert d["dispatch_chain_steps"] == [{"order": 1, "department_code": "平台运维组"}]
    assert d["dispatch_step_index"] == 0
    # 能力位随之更新：2302 是末级
    assert d["can_refine"] is False

    assert await action_sequence(renv, t["id"]) == ["create", "refine"]
    factory = async_sessionmaker_for(renv["engine"])
    async with factory() as s:
        log = (await s.execute(
            select(TicketStateLog).where(
                TicketStateLog.ticket_id == t["id"],
                TicketStateLog.action_type == "refine",
            )
        )).scalar_one()
        assert log.from_state == "pending" and log.to_state == "pending"
        assert "业务保障" in log.reason and "应用平台" in log.reason


async def test_return_after_refine_restores_category_and_department(renv):
    t = await renv["create_ticket"]()
    await renv["refine"](t["id"], 2302)
    d = await renv["patch"](t["id"], {"state": "returned", "reason": "重新判断问题"})
    assert d["state"] == "pending"
    assert d["category_id"] == 2301
    assert d["skill_group_name"] == "售后"
    assert d["dispatcher_id"] == renv["aftersale_user"]


async def set_existing_open_ticket(renv, ticket_id):
    """Model a ticket that reached open before the judgement gate was added."""
    from app.models.ticket import Ticket
    factory = async_sessionmaker_for(renv["engine"])
    async with factory() as db:
        ticket = await db.get(Ticket, ticket_id)
        ticket.state = "open"
        ticket.owner_id = renv["aftersale_user"]
        await db.commit()


async def test_refine_open_switches_owner(renv):
    """open 分诊换部门时同步换成新部门的默认处理人，状态保持 open。"""
    t = await renv["create_ticket"]()
    await set_existing_open_ticket(renv, t["id"])

    d = await renv["refine"](t["id"], 2302)
    assert d["state"] == "open"
    assert d["owner_id"] == renv["platform_user"]
    assert d["skill_group_name"] == "平台运维组"


async def test_refine_continue_rule_same_dept(renv):
    """接续规则：新链首步 == 当前判断部门（售后）→ 单步链原地不动，owner 保留。"""
    t = await renv["create_ticket"]()
    await set_existing_open_ticket(renv, t["id"])

    d = await renv["refine"](t["id"], 2322)  # 硬件故障：判断方=处理方
    assert d["state"] == "open"
    assert d["category_id"] == 2322
    assert d["skill_group_name"] == "售后"
    assert d["owner_id"] == renv["aftersale_user"]
    assert d["dispatch_chain_steps"] == [{"order": 1, "department_code": "售后"}]
    assert d["dispatch_step_index"] == 0


async def test_refine_reject_non_child(renv):
    """只能细化到直下级：2301 → 2311（属于 2310 分支）→ 400。"""
    t = await renv["create_ticket"]()
    await renv["refine"](t["id"], 2311, expect=400)


async def test_refine_reject_missing_category(renv):
    t = await renv["create_ticket"]()
    await renv["refine"](t["id"], 999999, expect=404)


async def test_refine_reject_leaf(renv):
    """末级分类无可细化对象：分诊一次到 2302 后再次分诊 → 403。"""
    t = await renv["create_ticket"]()
    await renv["refine"](t["id"], 2302)
    resp = await renv["refine"](t["id"], 2310, expect=403)
    assert "判断末级" in resp.json()["error"]["message"]


async def test_refine_requires_judging_dept_member(renv):
    """非判断部门成员无权分诊（admin 之外按部门成员判定）。"""
    t = await renv["create_ticket"]()
    outsider = type("_U", (), {"id": 999999, "group_id": None, "role": "agent", "is_active": True})()
    with as_user(outsider.id, "agent"):
        r = await renv["client"].post(
            f"/api/v1/tickets/{t['id']}/refine", json={"category_id": 2302}
        )
    assert r.status_code == 403
    assert "售后" in r.json()["error"]["message"]


async def test_refine_denied_in_terminal_state(renv):
    """已处理的工单不可回溯分诊。"""
    t = await renv["create_ticket"]()
    await set_existing_open_ticket(renv, t["id"])
    await renv["patch"](t["id"], {"state": "resolved", "solution": "已解决"})
    resp = await renv["refine"](t["id"], 2302, expect=403)
    assert "仅待受理/处理中" in resp.json()["error"]["message"]
