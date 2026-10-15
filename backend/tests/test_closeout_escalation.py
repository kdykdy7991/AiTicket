"""收尾（设计 §5.2 / §8.2 #6、#9）：投诉升级链 + 回访不满意原因。

- complaint_escalation_policies.escalation_chain：动态角色升级链
  （一般 NULL / 重要 [部门负责人] / 重大 [部门负责人 → 分管领导]），
  migration l6o8p9q0r1s2 播种；
- tickets.unsatisfied_reason：dissatisfied 必填、退回重开后保留、
  新一轮非不满意回访清空；回访事实保护路径不误删。
"""

from datetime import datetime, timezone
from pathlib import Path

import pytest_asyncio
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.complaint import ComplaintEscalationPolicy
from app.models.group import SkillGroup, UserSkillGroup
from app.models.user import User

from test_transition_baseline import _next_phone

LEADER_CHAIN = [{"order": 1, "role": "dept_leader", "label": "涉及部门负责人"}]
CRITICAL_CHAIN = LEADER_CHAIN + [{"order": 2, "role": "division_leader", "label": "分管领导"}]


@pytest_asyncio.fixture
async def closeout_env(client):
    """工单闭环辅助 + 升级策略重播（测试库逐用例 TRUNCATE 后按 migration 值回填）。"""
    c, dispatcher_id, engine = client
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        # 升级策略（值与 migration l6o8p9q0r1s2 播种一致）
        now = datetime.now(timezone.utc)
        s.add_all([
            ComplaintEscalationPolicy(
                complaint_level="一般", sla_resolution_multiplier=1.0,
                required_role="agent", escalation_chain=None,
                note="默认 一般", created_at=now, updated_at=now,
            ),
            ComplaintEscalationPolicy(
                complaint_level="重要", sla_resolution_multiplier=0.75,
                required_role="manager", escalation_chain=LEADER_CHAIN,
                note="默认 重要", created_at=now, updated_at=now,
            ),
            ComplaintEscalationPolicy(
                complaint_level="重大", sla_resolution_multiplier=0.5,
                required_role="admin", escalation_chain=CRITICAL_CHAIN,
                note="默认 重大", created_at=now, updated_at=now,
            ),
        ])
        # 协调部门 + 对接人 + 处理人
        sg = SkillGroup(name="收尾测试部门")
        s.add(sg)
        await s.flush()
        s.add(UserSkillGroup(user_id=dispatcher_id, skill_group_id=sg.id, is_dispatcher=True))
        handler = User(username="closeout-handler", name="收尾处理人", password_hash="x", role="agent")
        s.add(handler)
        await s.flush()
        # 处理人必须属于工单当前责任部门（分派时后端会校验）
        s.add(UserSkillGroup(user_id=handler.id, skill_group_id=sg.id, is_dispatcher=False))
        await s.commit()
        await s.refresh(sg)
        await s.refresh(handler)

    async def create_ticket(**kw):
        payload = dict(
            description="closeout test",
            priority="p3_normal",
            channel="phone",
            customer_type="personal",
            customer_phone=_next_phone(),
            dispatcher_id=dispatcher_id,
            skill_group_id=sg.id,
        )
        payload.update(kw)
        r = await c.post("/api/v1/tickets", json=payload)
        assert r.status_code == 201, r.text
        return r.json()["data"]

    async def dispatch_and_resolve(ticket_id):
        r = await c.patch(f"/api/v1/tickets/{ticket_id}",
                          json={"state": "open", "owner_id": handler.id})
        assert r.status_code == 200, r.text
        r = await c.patch(f"/api/v1/tickets/{ticket_id}", json={"state": "resolved"})
        assert r.status_code == 200, r.text

    return {
        "client": c,
        "engine": engine,
        "factory": factory,
        "handler_id": handler.id,
        "create_ticket": create_ticket,
        "dispatch_and_resolve": dispatch_and_resolve,
    }


# ── escalation_chain ──────────────────────────────────────


async def test_migration_revision_applied(closeout_env):
    """测试库 alembic_version 含本收尾 migration（列/播种由 upgrade head 落地）。"""
    factory = async_sessionmaker(closeout_env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        head = (await s.execute(text("SELECT version_num FROM alembic_version"))).scalar_one()
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    assert head == ScriptDirectory.from_config(config).get_current_head()


async def test_escalation_chain_shape(closeout_env):
    """升级链形状：一般 NULL / 重要 [dept_leader] / 重大 [dept_leader → division_leader]。"""
    factory = async_sessionmaker(closeout_env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        rows = (await s.execute(select(ComplaintEscalationPolicy))).scalars().all()
    by_level = {r.complaint_level: r for r in rows}

    assert by_level["一般"].escalation_chain is None, "一般走 dispatch_chain → 值班组，无升级链"
    assert by_level["重要"].escalation_chain == LEADER_CHAIN
    assert by_level["重大"].escalation_chain == CRITICAL_CHAIN
    # order 语义同构 dispatch_chains.steps：1 起、连续
    orders = [step["order"] for step in by_level["重大"].escalation_chain]
    assert orders == [1, 2]
    assert all({"order", "role", "label"} <= set(step) for step in by_level["重大"].escalation_chain)


# ── unsatisfied_reason ────────────────────────────────────


async def test_dissatisfied_requires_reason(closeout_env):
    """dissatisfied 无原因 → 422，且本轮满意度不落库（事务回滚）。"""
    c = closeout_env["client"]
    t = await closeout_env["create_ticket"]()
    await closeout_env["dispatch_and_resolve"](t["id"])

    r = await c.patch(f"/api/v1/tickets/{t['id']}", json={
        "is_callbacked": True, "satisfaction": "dissatisfied",
        "callback_details": "客户不满意",
    })
    assert r.status_code == 422, r.text
    assert "不满意原因" in r.json()["detail"]

    d = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    assert d["satisfaction"] is None, "校验失败不应留下半截回访事实"
    assert d["unsatisfied_reason"] is None


async def test_dissatisfied_with_reason_roundtrip(closeout_env):
    """带原因的不满意回访：200，详情序列化 unsatisfied_reason。"""
    c = closeout_env["client"]
    t = await closeout_env["create_ticket"]()
    await closeout_env["dispatch_and_resolve"](t["id"])

    r = await c.patch(f"/api/v1/tickets/{t['id']}", json={
        "is_callbacked": True, "satisfaction": "dissatisfied",
        "unsatisfied_reason": "  上门两次未修复  ",
        "callback_details": "客户不满意",
    })
    assert r.status_code == 200, r.text
    d = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    assert d["satisfaction"] == "dissatisfied"
    assert d["unsatisfied_reason"] == "上门两次未修复"  # strip 后存储
    # 不满意仍被归档前置拦截
    r2 = await c.patch(f"/api/v1/tickets/{t['id']}", json={"state": "archived"})
    assert r2.status_code == 422


async def test_reason_survives_reopen(closeout_env):
    """退回重开：satisfaction 清空，unsatisfied_reason 保留（处理人要看到改什么）。"""
    c = closeout_env["client"]
    t = await closeout_env["create_ticket"]()
    await closeout_env["dispatch_and_resolve"](t["id"])
    r = await c.patch(f"/api/v1/tickets/{t['id']}", json={
        "is_callbacked": True, "satisfaction": "dissatisfied",
        "unsatisfied_reason": "定位错误，未解决根本问题",
    })
    assert r.status_code == 200, r.text

    r = await c.patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "open", "reason": "客户反馈未解决，重新处理",
    })
    assert r.status_code == 200, r.text

    d = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    assert d["satisfaction"] is None
    assert d["unsatisfied_reason"] == "定位错误，未解决根本问题"


async def test_reason_cleared_by_new_satisfied_callback(closeout_env):
    """新一轮回访为非不满意：unsatisfied_reason 随之清空。"""
    c = closeout_env["client"]
    t = await closeout_env["create_ticket"]()
    await closeout_env["dispatch_and_resolve"](t["id"])
    await c.patch(f"/api/v1/tickets/{t['id']}", json={
        "is_callbacked": True, "satisfaction": "dissatisfied",
        "unsatisfied_reason": "首次未解决",
    })
    # 重开 → 新一轮满意回访（回访字段与状态无关，is_callbacked 仍为 True）
    r0 = await c.patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "open", "reason": "退回重新处理",
    })
    assert r0.status_code == 200, r0.text

    r = await c.patch(f"/api/v1/tickets/{t['id']}", json={
        "is_callbacked": True, "satisfaction": "satisfied",
        "callback_details": "二次处理后满意",
    })
    assert r.status_code == 200, r.text
    d = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    assert d["satisfaction"] == "satisfied"
    assert d["unsatisfied_reason"] is None


async def test_callback_fact_protection_keeps_reason(closeout_env):
    """is_callbacked=false 关不掉不满意事实：satisfaction 与 unsatisfied_reason 均保留。"""
    c = closeout_env["client"]
    t = await closeout_env["create_ticket"]()
    await closeout_env["dispatch_and_resolve"](t["id"])
    await c.patch(f"/api/v1/tickets/{t['id']}", json={
        "is_callbacked": True, "satisfaction": "dissatisfied",
        "unsatisfied_reason": "设备仍离线",
    })

    r = await c.patch(f"/api/v1/tickets/{t['id']}", json={"is_callbacked": False})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["satisfaction"] == "dissatisfied"
    assert d["unsatisfied_reason"] == "设备仍离线"

    r = await c.patch(f"/api/v1/tickets/{t['id']}", json={"callback_required": False})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["satisfaction"] == "dissatisfied"
    assert d["unsatisfied_reason"] == "设备仍离线"
