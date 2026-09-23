"""Phase 9 — 客服工单全流程架构回归（V0.86 最小架构改造收尾）。

在"状态流转收口"之后，验证端到端链路仍然成立，且 Flow Log 动作完整：
  1. 标准闭环：建单 → 分派 → 处理说明(resolved) → 回访满意 → 归档
  2. 异常分支链：暂缓 → 恢复 → 打回 → 退回 → 重新提交 → 撤销
  3. 不满意闭环：dissatisfied 被拦截 → 退回重开 → 再处理 → 满意归档
  4. action_type 完整性：链路上每条 Flow Log 都有动作类型（无 NULL/未知值）

与 test_transition_baseline.py 的关系：基线文件按"单条流转契约"组织，
本文件按"业务闭环链路"组织，覆盖跨阶段串联回归。
"""

from contextlib import contextmanager

import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.deps import get_current_user
from app.main import app
from app.models.group import SkillGroup, UserSkillGroup
from app.models.ticket import Ticket, TicketStateLog
from app.models.user import User
from app.services.state_machine import ACTION_TYPES

_PHONE_SEQ = [2000]

import pytest


def _next_phone() -> str:
    _PHONE_SEQ[0] += 1
    return f"1390001{_PHONE_SEQ[0]:04d}"


@pytest_asyncio.fixture
async def env(client):
    c, dispatcher_id, engine = client
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        sg = SkillGroup(name="回归协调组")
        s.add(sg)
        await s.flush()
        s.add(UserSkillGroup(user_id=dispatcher_id, skill_group_id=sg.id, is_dispatcher=True))
        handler = User(username="wf-handler", name="回归处理人", password_hash="x", role="agent")
        s.add(handler)
        await s.commit()
        await s.refresh(sg)
        await s.refresh(handler)

    async def create_ticket(**kw):
        payload = dict(
            description="workflow regression",
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

    async def patch(tid, payload, expect=200):
        r = await c.patch(f"/api/v1/tickets/{tid}", json=payload)
        assert r.status_code == expect, r.text
        return r.json() if expect == 200 else r

    return {
        "client": c, "engine": engine, "factory": factory,
        "dispatcher_id": dispatcher_id, "handler_id": handler.id, "sg_id": sg.id,
        "create_ticket": create_ticket, "patch": patch,
    }


@contextmanager
def as_user(user_id: int, role: str, group_id: int | None = None):
    fake = type("_FakeUser", (), {"id": user_id, "group_id": group_id, "role": role, "is_active": True})()
    original = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: fake
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = original


async def action_sequence(env, ticket_id) -> list[str]:
    """按时间顺序取该工单所有 Flow Log 的 action_type。"""
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        logs = list((await s.execute(
            select(TicketStateLog)
            .where(TicketStateLog.ticket_id == ticket_id)
            .order_by(TicketStateLog.id)
        )).scalars().all())
    assert logs, "工单必须有 Flow Log"
    for log in logs:
        assert log.action_type is not None, f"log#{log.id} 缺少 action_type"
        assert log.action_type in ACTION_TYPES, f"log#{log.id} action_type 未知: {log.action_type}"
    return [log.action_type for log in logs]


async def test_standard_closed_loop(env):
    """标准闭环：建单 → 分派 → 处理说明 → 回访满意 → 归档。"""
    c = env["client"]
    t = await env["create_ticket"]()

    # 1) 待受理：后端下发分派动作（requires_owner）
    d = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    dispatch = {a["action"]: a for a in d["allowed_actions"]}["dispatch"]
    assert dispatch["requires_owner"] is True

    # 2) 分派
    r = await env["patch"](t["id"], {"state": dispatch["target_state"], "owner_id": env["handler_id"]})
    assert r["state"] == "open"

    # 3) 处理人提交处理说明 → resolved
    with as_user(env["handler_id"], "agent"):
        r2 = await c.post(f"/api/v1/tickets/{t['id']}/articles",
                          data={"type": "reply", "body": "更换备件并复测通过"})
    assert r2.status_code == 201, r2.text

    d = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    archive = {a["action"]: a for a in d["allowed_actions"]}["archive"]
    assert archive["requires_reason"] is False

    # 4) 回访满意并归档（带 callback_details）
    r3 = await env["patch"](t["id"], {
        "state": archive["target_state"],
        "is_callbacked": True, "callback_required": True,
        "satisfaction": "satisfied",
        "callback_details": "回访确认设备运行正常",
        "archive_notes": "闭环",
    })
    assert r3["state"] == "archived"
    assert r3["callback_details"] == "回访确认设备运行正常"

    # 5) 终态：无动作、能力位全关
    d = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    assert d["allowed_actions"] == [] and d["is_terminal"] is True
    assert not (d["can_reply"] or d["can_addition"] or d["can_remind"])

    # 6) Flow Log 动作序列完整
    assert await action_sequence(env, t["id"]) == ["create", "dispatch", "resolve", "archive"]


async def test_exception_branch_chain(env):
    """异常分支链：暂缓 → 恢复 → 打回 → 退回 → 重新提交 → 撤销。"""
    t = await env["create_ticket"]()
    await env["patch"](t["id"], {"state": "open", "owner_id": env["handler_id"]})

    # 暂缓 / 恢复（处理人执行）
    with as_user(env["handler_id"], "agent"):
        await env["patch"](t["id"], {"state": "on_hold", "reason": "等待备件"})
        await env["patch"](t["id"], {"state": "open", "reason": "备件已到"})
        # 打回：处理人 → 待受理
        await env["patch"](t["id"], {"state": "pending", "reason": "信息不全，打回重新分派"})

    # 退回：待受理 → 已退回
    await env["patch"](t["id"], {"state": "returned", "reason": "需客户补充合同"})
    # 重新提交：已退回 → 待受理
    await env["patch"](t["id"], {"state": "pending"})
    # 撤销
    await env["patch"](t["id"], {"state": "cancelled", "reason": "客户取消诉求"})

    assert await action_sequence(env, t["id"]) == [
        "create", "dispatch", "hold", "resume", "return",
        "return", "resubmit", "cancel",
    ]


async def test_dissatisfied_closure_loop(env):
    """不满意闭环：拦截归档 → 退回重开 → 再处理 → 满意后归档。"""
    c = env["client"]
    t = await env["create_ticket"]()
    await env["patch"](t["id"], {"state": "open", "owner_id": env["handler_id"]})
    with as_user(env["handler_id"], "agent"):
        r = await c.post(f"/api/v1/tickets/{t['id']}/articles",
                         data={"type": "reply", "body": "首次处理"})
    assert r.status_code == 201, r.text

    # 回访：不满意（带原因）
    await env["patch"](t["id"], {
        "is_callbacked": True, "satisfaction": "dissatisfied",
        "callback_details": "问题仍复现，客户不满意",
    })

    # 归档被拦截：动作不下发 + 执行 422
    d = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    assert "archive" not in [a["action"] for a in d["allowed_actions"]]
    rr = await c.patch(f"/api/v1/tickets/{t['id']}", json={"state": "archived"})
    assert rr.status_code == 422

    # 正确出口：退回重开
    d = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    reopen = {a["action"]: a for a in d["allowed_actions"]}["reopen"]
    await env["patch"](t["id"], {"state": reopen["target_state"], "reason": "客户反馈未解决，重新处理"})

    # 重开副作用：上一轮回访满意度失效（否则不满意将永久隐藏归档动作，
    # 重开后再也无法完成闭环）；不满意原因保留在 callback_details 作历史
    d0 = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    assert d0["satisfaction"] is None
    assert d0["callback_details"] == "问题仍复现，客户不满意"

    # 再处理
    with as_user(env["handler_id"], "agent"):
        r2 = await c.post(f"/api/v1/tickets/{t['id']}/articles",
                          data={"type": "reply", "body": "二次处理完成"})
    assert r2.status_code == 201, r2.text

    # 再回访：满意 → 归档
    d = (await c.get(f"/api/v1/tickets/{t['id']}")).json()
    archive = {a["action"]: a for a in d["allowed_actions"]}["archive"]
    r3 = await env["patch"](t["id"], {
        "state": archive["target_state"],
        "is_callbacked": True, "callback_required": True,
        "satisfaction": "satisfied",
        "callback_details": "二次处理后确认解决，客户满意",
    })
    assert r3["state"] == "archived"

    assert await action_sequence(env, t["id"]) == [
        "create", "dispatch", "resolve", "reopen", "resolve", "archive",
    ]


async def test_instant_resolve_action_type(env):
    """即时办结：None → archived 的一次性日志动作完整，终态副作用唯一归属执行入口。"""
    r = await env["client"].post("/api/v1/tickets", json={
        "description": "回归-即时办结", "priority": "p4_enterprise",
        "channel": "phone", "customer_type": "personal",
        "customer_phone": _next_phone(),
        "is_instant_resolve": True, "instant_resolution": "已在线答复",
    })
    assert r.status_code == 201, r.text
    tid = r.json()["data"]["id"]
    assert await action_sequence(env, tid) == ["instant_resolve"]

    # 分工核验：resolved/solved_at/resolution 为建单初始化数据（调用方负责）；
    # closed_at / closed_duration_minutes / TicketStateLog 由 apply_initial_state
    # （执行入口）唯一计算，构造期不再重复维护
    async with env["factory"]() as s:
        tk = (await s.execute(select(Ticket).where(Ticket.id == tid))).scalar_one()
        assert tk.resolved is True and tk.solved_at is not None   # 初始化数据
        assert tk.closed_at is not None                           # 执行入口副作用
        assert tk.closed_duration_minutes == 0
        assert tk.state == "archived"
