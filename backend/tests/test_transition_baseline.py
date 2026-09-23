"""Phase 1 — 状态流转基线测试（重构前锁死当前应保留的客服工单行为）。

覆盖范围（见 docs/ticket_architecture_refactor_result.md Phase 1）:
  1. validate_transition / requires_reason / terminal state（纯单元）
  2. pending → open     : owner / first_owner_id / state log
  3. open → resolved    : solved_at / resolved / SLA breach / state log
  4. resolved → open    : reopen / has_returned
  5. pending → returned : returned_to_user / owner / reason 必填
  6. returned → pending : 清理 owner / 无需 reason / has_returned 复位
  7. open ↔ on_hold     : reason 必填 / hold_until 落库
  8. archived / cancelled : closed_at / closed_duration_minutes
  9. batch-update       : 合法性 + 权限 + reason + 状态副作用（Phase 3 起与单条
                          PATCH 同源走 apply_transition，原 4 个缺口 xfail 已转正）

约定:
- 标注 xfail 的用例表达"期望的正确行为"，用于暴露已知缺陷，
  不为旧的错误行为背书；修复后移除 xfail 标记转为普通用例。
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.deps import get_current_user
from app.core.exceptions import StateTransitionError
from app.main import app
from app.models.group import SkillGroup, UserSkillGroup
from app.models.ticket import Ticket, TicketStateLog
from app.models.user import User
from app.services.state_machine import (
    TERMINAL_STATES,
    TRANSITIONS,
    validate_initial_state,
    validate_transition,
    requires_reason,
)

# ── 唯一电话计数器，避免建单查重警告互相干扰 ─────────────────
_PHONE_SEQ = [1000]


def _next_phone() -> str:
    _PHONE_SEQ[0] += 1
    return f"1390000{_PHONE_SEQ[0]:04d}"


# ── Fixtures ─────────────────────────────────────────────


@pytest_asyncio.fixture
async def env(client):
    """协调部门 + 对接人 + 处理人 + 一个建单辅助函数。"""
    c, dispatcher_id, engine = client
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        sg = SkillGroup(name="TB协调组")
        s.add(sg)
        await s.flush()
        s.add(UserSkillGroup(user_id=dispatcher_id, skill_group_id=sg.id, is_dispatcher=True))
        handler = User(username="tb-handler", name="基线处理人", password_hash="x", role="agent")
        s.add(handler)
        await s.commit()
        await s.refresh(sg)
        await s.refresh(handler)

    async def create_ticket(**kw):
        payload = dict(
            description="transition baseline",
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

    async def dispatch(ticket_id, owner_id):
        r = await c.patch(f"/api/v1/tickets/{ticket_id}", json={"state": "open", "owner_id": owner_id})
        assert r.status_code == 200, r.text
        return r.json()

    async def resolve(ticket_id):
        r = await c.patch(f"/api/v1/tickets/{ticket_id}", json={"state": "resolved"})
        assert r.status_code == 200, r.text
        return r.json()

    return {
        "client": c,
        "engine": engine,
        "factory": factory,
        "dispatcher_id": dispatcher_id,
        "handler_id": handler.id,
        "sg_id": sg.id,
        "create_ticket": create_ticket,
        "dispatch": dispatch,
        "resolve": resolve,
    }


@contextmanager
def as_user(user_id: int, role: str, group_id: int | None = None):
    """临时切换 get_current_user 身份（用于非 admin 权限测试）。"""
    fake = type("_FakeUser", (), {"id": user_id, "group_id": group_id, "role": role, "is_active": True})()
    original = app.dependency_overrides[get_current_user]
    app.dependency_overrides[get_current_user] = lambda: fake
    try:
        yield
    finally:
        app.dependency_overrides[get_current_user] = original


async def db_ticket(env, ticket_id) -> Ticket:
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        return (await s.execute(select(Ticket).where(Ticket.id == ticket_id))).scalar_one()


async def db_logs(env, ticket_id) -> list[TicketStateLog]:
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        return list((await s.execute(
            select(TicketStateLog).where(TicketStateLog.ticket_id == ticket_id).order_by(TicketStateLog.id)
        )).scalars().all())


# ── 1. 状态机纯单元测试 ──────────────────────────────────


def test_validate_transition_accepts_legal_pairs():
    for frm, to in [
        ("pending", "open"), ("pending", "returned"), ("pending", "cancelled"),
        ("open", "resolved"), ("open", "on_hold"), ("open", "pending"), ("open", "cancelled"),
        ("on_hold", "resolved"), ("on_hold", "open"), ("on_hold", "cancelled"),
        ("resolved", "archived"), ("resolved", "open"), ("resolved", "on_hold"),
        ("returned", "pending"), ("returned", "cancelled"),
    ]:
        validate_transition(frm, to)  # 不抛异常即通过


def test_validate_transition_rejects_illegal_pairs():
    for frm, to in [
        ("pending", "resolved"),   # 跳过处理
        ("pending", "archived"),   # 建单时才允许的初始目标
        ("open", "archived"),      # 必须先 resolved
        ("returned", "open"),      # 退回后须先回 pending
        ("on_hold", "pending"),
    ]:
        with pytest.raises(StateTransitionError):
            validate_transition(frm, to)


def test_terminal_states_cannot_transition():
    assert TERMINAL_STATES == {"archived", "cancelled"}
    for term in TERMINAL_STATES:
        assert TRANSITIONS[term] == []
        for to in ("pending", "open", "resolved", "archived", "cancelled"):
            with pytest.raises(StateTransitionError):
                validate_transition(term, to)


def test_validate_initial_state():
    validate_initial_state("pending")
    validate_initial_state("archived")
    for bad in ("open", "resolved", "cancelled"):
        with pytest.raises(StateTransitionError):
            validate_initial_state(bad)


def test_requires_reason_matrix():
    # 需要原因
    assert requires_reason("pending", "returned") is True   # 客户/客服退回
    assert requires_reason("pending", "cancelled") is True  # 撤销
    assert requires_reason("open", "pending") is True       # 处理人打回
    assert requires_reason("open", "on_hold") is True       # 暂缓
    assert requires_reason("on_hold", "open") is True       # 恢复处理
    assert requires_reason("resolved", "on_hold") is True   # （会被业务约束改写为 open）
    assert requires_reason("resolved", "open") is True      # 退回重开
    assert requires_reason("returned", "cancelled") is True
    # 不需要原因
    assert requires_reason("pending", "open") is False      # 分派
    assert requires_reason("open", "resolved") is False     # 提交处理说明
    assert requires_reason("resolved", "archived") is False
    assert requires_reason("returned", "pending") is False  # 重新提交


# ── 2. pending → open（分派） ───────────────────────────


async def test_dispatch_pending_to_open(env):
    t = await env["create_ticket"]()
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "open", "owner_id": env["handler_id"],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "open"
    assert d["owner_id"] == env["handler_id"]
    # 快照：进入 open 时记录了被指派的处理人
    logs = await db_logs(env, t["id"])
    last = logs[-1]
    assert (last.from_state, last.to_state) == ("pending", "open")
    assert last.operator_id is not None
    assert last.owner_id_snapshot == env["handler_id"]
    # 进入新状态的停留时长（由建单日志推算，单位分钟）
    assert last.duration_minutes is not None


async def test_dispatch_records_first_owner_as_assigned_handler(env):
    """first_owner = 被指派的首任处理人（语义见 docs/07_requirements_supplement.md:42、
    PPT_Part1:138「first_owner=王工」）。Phase 2 起由 apply_transition 收口保证。"""
    t = await env["create_ticket"]()
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "open", "owner_id": env["handler_id"],
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["first_owner_id"] == env["handler_id"], (
        f"first_owner 应为被指派处理人 {env['handler_id']}，实际 {d['first_owner_id']}"
    )


async def test_dispatch_requires_reason_none(env):
    """分派不需要填写原因（requires_reason=False 的现状）。"""
    t = await env["create_ticket"]()
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "open", "owner_id": env["handler_id"]})
    assert r.status_code == 200


# ── 3. open → resolved ─────────────────────────────────


async def test_resolve_open_to_resolved(env):
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "resolved", "root_cause": "参数配置异常", "solution": "更新配置并验证",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "resolved"
    assert d["solved_at"] is not None
    assert d["resolved"] is True
    assert d["sla_solution_breached"] is False
    # 注：solution_deadline 是否有值取决于该 priority/协调组是否有命中 SLA 策略，
    # 不属于流转契约，breach 标记由 test_resolve_sets_sla_breach_when_overdue 单独覆盖
    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("open", "resolved")


async def test_resolve_sets_sla_breach_when_overdue(env):
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    # 手动把截止时间改到过去
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        tk = (await s.execute(select(Ticket).where(Ticket.id == t["id"]))).scalar_one()
        tk.solution_deadline = datetime.now(timezone.utc) - timedelta(hours=1)
        await s.commit()
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "resolved"})
    assert r.status_code == 200, r.text
    assert r.json()["sla_solution_breached"] is True


async def test_resolve_keeps_owner_contract(env):
    """resolved 状态 owner 不变（处理人提交方案的现行契约）。"""
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "resolved"})
    assert r.json()["owner_id"] == env["handler_id"]


# ── 4. resolved → open（退回重开） ──────────────────────


async def test_reopen_resolved_to_open(env):
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    await env["resolve"](t["id"])
    # requires_reason(resolved→open)=True：退回重开必须填原因
    r0 = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "open"})
    assert r0.status_code == 400, r0.text
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "open", "reason": "客户反馈未解决",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "open"
    # 现状：resolved→open 不属于 RETURN_TRANSITIONS，has_returned 复位为 False
    assert d["has_returned"] is False
    # 现状：solved_at / resolved 保留（记录"曾经解决"，本次不改此语义）
    assert d["solved_at"] is not None
    assert d["resolved"] is True
    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("resolved", "open")


async def test_resolved_to_on_hold_rewritten_to_open(env):
    """业务约束：resolved→on_hold 自动改写为 resolved→open。"""
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    await env["resolve"](t["id"])
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "on_hold", "reason": "客户要求暂缓",
    })
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "open"


# ── 5. pending → returned ──────────────────────────────


async def test_return_pending_to_returned(env):
    t = await env["create_ticket"]()
    creator_id = t["creator_id"]
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "returned", "reason": "客户不认可受理方案",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "returned"
    assert d["has_returned"] is True
    assert d["returned_to_user_id"] == creator_id
    assert d["owner_id"] == creator_id
    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("pending", "returned")
    assert logs[-1].reason == "客户不认可受理方案"


async def test_return_requires_reason(env):
    t = await env["create_ticket"]()
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "returned"})
    assert r.status_code == 400, r.text
    assert "需要填写原因" in r.text


# ── 6. returned → pending（重新提交） ───────────────────


async def test_resubmit_returned_to_pending(env):
    t = await env["create_ticket"]()
    await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "returned", "reason": "信息不全",
    })
    # 重新提交不要求 reason（requires_reason=False 现状）
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "pending"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "pending"
    assert d["owner_id"] is None          # 清空处理人，等待再次分派
    assert d["returned_to_user_id"] is None
    assert d["has_returned"] is False     # returned→pending 不属于 RETURN_TRANSITIONS
    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("returned", "pending")


# ── 7. open ↔ on_hold ──────────────────────────────────


async def test_hold_open_to_on_hold(env):
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    # 缺 reason → 400
    r0 = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "on_hold"})
    assert r0.status_code == 400, r0.text
    # 带 reason + hold_until → 200
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "on_hold", "reason": "等待备件", "hold_until": "2027-03-01T00:00:00",
    })
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "on_hold"
    tk = await db_ticket(env, t["id"])
    assert tk.hold_until is not None      # hold_until 不在 detail 里暴露，直接查库
    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("open", "on_hold")
    assert logs[-1].reason == "等待备件"


async def test_resume_on_hold_to_open(env):
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "on_hold", "reason": "等待备件",
    })
    # 恢复处理也需要 reason（requires_reason on_hold→open=True 现状）
    r0 = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "open"})
    assert r0.status_code == 400, r0.text
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "open", "reason": "备件已到"})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "open"
    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("on_hold", "open")


# ── 8. 终态：archived / cancelled ───────────────────────


async def test_cancel_pending_sets_closed_fields(env):
    t = await env["create_ticket"]()
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "cancelled", "reason": "客户主动取消",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "cancelled"
    assert d["closed_at"] is not None
    assert d["closed_duration_minutes"] is not None
    assert d["closed_duration_minutes"] >= 0
    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("pending", "cancelled")


async def test_archive_resolved_sets_closed_fields(env):
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    await env["resolve"](t["id"])
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "archived", "is_callbacked": True, "callback_required": False,
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "archived"
    assert d["closed_at"] is not None
    assert d["closed_duration_minutes"] >= 0
    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("resolved", "archived")


async def test_terminal_state_rejects_transition(env):
    t = await env["create_ticket"]()
    await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "cancelled", "reason": "关闭",
    })
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "open"})
    assert r.status_code == 400, r.text
    assert "INVALID_STATE_TRANSITION" in r.text


# ── 9. batch-update：现状 + 三个已知缺口 ────────────────


async def test_batch_illegal_transition_skipped(env):
    """现状（保留）：非法流转被跳过，工单状态与日志都不变。"""
    t = await env["create_ticket"]()
    before = len(await db_logs(env, t["id"]))
    r = await env["client"].post("/api/v1/tickets/batch-update", json={
        "ticket_ids": [t["id"]], "updates": {"state": "resolved"},  # pending→resolved 非法
    })
    assert r.status_code == 200, r.text
    tk = await db_ticket(env, t["id"])
    assert tk.state == "pending"
    assert len(await db_logs(env, t["id"])) == before


async def test_batch_state_change_writes_log(env):
    """现状（保留）：batch 状态变更写 state log 与人员快照。"""
    t = await env["create_ticket"]()
    r = await env["client"].post("/api/v1/tickets/batch-update", json={
        "ticket_ids": [t["id"]], "updates": {"state": "open", "owner_id": env["handler_id"]},
    })
    assert r.status_code == 200, r.text
    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("pending", "open")
    assert logs[-1].owner_id_snapshot == env["handler_id"]


async def test_batch_dispatch_requires_permission(env):
    """期望：与单条 PATCH 一致——无权限者 batch 分派被拒绝(403)。"""
    # 一个与该工单无关的 agent
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        outsider = User(username="tb-outsider", name="无关客服", password_hash="x", role="agent")
        s.add(outsider)
        await s.commit()
        await s.refresh(outsider)
        outsider_id, outsider_role, outsider_group = outsider.id, outsider.role, outsider.group_id

    t = await env["create_ticket"]()
    with as_user(outsider_id, outsider_role, outsider_group):
        r = await env["client"].post("/api/v1/tickets/batch-update", json={
            "ticket_ids": [t["id"]], "updates": {"state": "open", "owner_id": env["handler_id"]},
        })
    assert r.status_code == 403, f"batch 应拒绝无权限流转，实际 {r.status_code}: {r.text}"
    tk = await db_ticket(env, t["id"])
    assert tk.state == "pending"


async def test_batch_return_requires_reason(env):
    t = await env["create_ticket"]()
    r = await env["client"].post("/api/v1/tickets/batch-update", json={
        "ticket_ids": [t["id"]], "updates": {"state": "returned"},
    })
    assert r.status_code == 400, f"batch 应要求退回原因，实际 {r.status_code}"
    tk = await db_ticket(env, t["id"])
    assert tk.state == "pending"


async def test_batch_resolve_side_effects_match_patch(env):
    """同一流转从 PATCH 与 batch 执行，最终业务结果必须一致。"""
    ta = await env["create_ticket"]()
    tb = await env["create_ticket"]()
    await env["dispatch"](ta["id"], env["handler_id"])
    await env["dispatch"](tb["id"], env["handler_id"])

    r1 = await env["client"].patch(f"/api/v1/tickets/{ta['id']}", json={"state": "resolved"})
    assert r1.status_code == 200, r1.text
    r2 = await env["client"].post("/api/v1/tickets/batch-update", json={
        "ticket_ids": [tb["id"]], "updates": {"state": "resolved"},
    })
    assert r2.status_code == 200, r2.text

    a, b = await db_ticket(env, ta["id"]), await db_ticket(env, tb["id"])
    assert a.state == b.state == "resolved"
    # 以下为一致性要求（当前 batch 缺失）
    assert b.solved_at is not None, "batch 应与 PATCH 一样写 solved_at"
    assert b.resolved is True, "batch 应与 PATCH 一样置 resolved=True"
    logs_a = await db_logs(env, ta["id"])
    logs_b = await db_logs(env, tb["id"])
    assert len(logs_b) == len(logs_a)


async def test_batch_terminal_sets_closed_at(env):
    t = await env["create_ticket"]()
    r = await env["client"].post("/api/v1/tickets/batch-update", json={
        "ticket_ids": [t["id"]], "updates": {"state": "cancelled", "reason": "批量撤销"},
    })
    assert r.status_code == 200, r.text
    tk = await db_ticket(env, t["id"])
    assert tk.state == "cancelled"
    assert tk.closed_at is not None, "batch 撤销应写 closed_at"
    assert tk.closed_duration_minutes is not None
