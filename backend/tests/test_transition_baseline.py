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


# ── 10. 文章回复路径（Phase 4 迁移至执行入口） ────────────


async def test_reply_transitions_to_resolved(env):
    """处理人提交处理说明 → open→resolved 统一走执行入口。"""
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    with as_user(env["handler_id"], "agent"):
        r = await env["client"].post(
            f"/api/v1/tickets/{t['id']}/articles",
            data={"type": "reply", "body": "已更换模块并复测通过"},
        )
    assert r.status_code == 201, r.text
    # 处理说明挂在新写入的 resolved 日志节点上（state_key = log.id）
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        from app.models.ticket import Article
        art = (await s.execute(
            select(Article).where(Article.ticket_id == t["id"], Article.type == "reply")
        )).scalar_one()
        assert art.state_key is not None and art.state_key.isdigit()

    d = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    assert d["state"] == "resolved"
    assert d["solved_at"] is not None
    assert d["resolved"] is True
    assert d["owner_id"] == env["handler_id"]

    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("open", "resolved")
    assert logs[-1].operator_id == env["handler_id"]
    assert logs[-1].duration_minutes is not None


async def test_reply_rejected_for_non_owner(env):
    """文章级规则保留：非当前处理人不能提交处理说明（403），且不产生任何流转。"""
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    with as_user(env["dispatcher_id"], "agent"):  # 对接人不是 owner
        r = await env["client"].post(
            f"/api/v1/tickets/{t['id']}/articles",
            data={"type": "reply", "body": "越权回复"},
        )
    assert r.status_code == 403, r.text
    tk = await db_ticket(env, t["id"])
    assert tk.state == "open"
    logs = await db_logs(env, t["id"])
    assert (logs[-1].from_state, logs[-1].to_state) == ("pending", "open")


# ── 11. 草稿提交初始日志（Phase 4 迁移至执行入口） ────────


async def test_draft_submit_writes_initial_log(env):
    c = env["client"]
    r = await c.post("/api/v1/tickets", json={
        "description": "草稿",
        "priority": "p3_normal",
        "channel": "phone",
        "customer_type": "personal",
        "customer_phone": _next_phone(),
        "dispatcher_id": env["dispatcher_id"],
        "skill_group_id": env["sg_id"],
        "is_draft": True,
    })
    assert r.status_code == 201, r.text
    draft = r.json()["data"]
    assert draft["number"] is None
    assert await db_logs(env, draft["id"]) == []  # 草稿不写初始日志

    r2 = await c.post(f"/api/v1/tickets/drafts/{draft['id']}/submit")
    assert r2.status_code == 200, r2.text
    submitted = r2.json()["data"]
    assert submitted["number"] is not None
    assert submitted["state"] == "pending"

    logs = await db_logs(env, draft["id"])
    assert len(logs) == 1
    assert logs[0].from_state is None and logs[0].to_state == "pending"
    assert logs[0].operator_id is not None


# ── 12. Flow Log action_type（Phase 5） ────────────────────


def test_action_map_covers_all_reachable_transitions():
    """动作表与真实流转表一一对应，且动作集合封闭。"""
    from app.services.state_machine import (
        ACTION_TYPES,
        TRANSITION_ACTIONS,
        action_for,
    )
    edges = {(None, "pending"), (None, "archived")}
    edges |= {(frm, to) for frm, tos in TRANSITIONS.items() for to in tos}
    assert edges == set(TRANSITION_ACTIONS.keys()), "动作表必须覆盖且仅覆盖真实可达流转"
    assert ACTION_TYPES == {
        "create", "instant_resolve", "dispatch", "return", "cancel",
        "resolve", "hold", "resume", "reopen", "archive", "resubmit",
    }
    assert action_for("pending", "open") == "dispatch"
    assert action_for("pending", "open", override="custom") == "custom"
    assert action_for("unknown", "unknown") is None


async def test_action_type_full_chain(env):
    """一条工单走完常规链路，每步 Flow Log 的 action_type 正确。"""
    t = await env["create_ticket"]()

    async def last_action():
        logs = await db_logs(env, t["id"])
        return logs[-1].action_type

    assert await last_action() == "create"              # None → pending
    await env["dispatch"](t["id"], env["handler_id"])
    assert await last_action() == "dispatch"            # pending → open
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "on_hold", "reason": "等待备件"})
    assert r.status_code == 200 and await last_action() == "hold"        # open → on_hold
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "open", "reason": "备件已到"})
    assert r.status_code == 200 and await last_action() == "resume"      # on_hold → open
    await env["resolve"](t["id"])
    assert await last_action() == "resolve"             # open → resolved
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "open", "reason": "客户反馈未解决"})
    assert r.status_code == 200 and await last_action() == "reopen"      # resolved → open
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "pending", "reason": "打回重新分派"})
    assert r.status_code == 200 and await last_action() == "return"      # open → pending
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "returned", "reason": "信息不全"})
    assert r.status_code == 200 and await last_action() == "return"      # pending → returned
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "pending"})
    assert r.status_code == 200 and await last_action() == "resubmit"    # returned → pending
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "cancelled", "reason": "客户取消"})
    assert r.status_code == 200 and await last_action() == "cancel"      # pending → cancelled


async def test_action_type_instant_and_archive(env):
    c = env["client"]
    # 即时办结：None → archived
    r = await c.post("/api/v1/tickets", json={
        "description": "咨询", "priority": "p4_enterprise",
        "channel": "phone", "customer_type": "personal",
        "customer_phone": _next_phone(),
        "is_instant_resolve": True, "instant_resolution": "已答复",
    })
    assert r.status_code == 201, r.text
    iid = r.json()["data"]["id"]
    ilogs = await db_logs(env, iid)
    assert ilogs[0].action_type == "instant_resolve"

    # 常规办结后归档：resolved → archived
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    await env["resolve"](t["id"])
    r2 = await c.patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "archived", "is_callbacked": True, "callback_required": False})
    assert r2.status_code == 200, r2.text
    logs = await db_logs(env, t["id"])
    assert logs[-1].action_type == "archive"


async def test_state_logs_endpoint_exposes_action_type(env):
    t = await env["create_ticket"]()
    r = await env["client"].get(f"/api/v1/tickets/{t['id']}/state-logs")
    assert r.status_code == 200, r.text
    entries = r.json()["data"]
    assert entries[-1]["action_type"] == "create"


async def test_action_type_nullable_for_history(env):
    """历史日志（迁移前）没有 action_type：DB 保持 NULL；接口按流转表推导兜底。"""
    t = await env["create_ticket"]()
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        s.add(TicketStateLog(
            ticket_id=t["id"], from_state="open", to_state="resolved",
            operator_id=env["dispatcher_id"], reason=None,
            # action_type 缺省 → NULL（模拟历史数据）
            creator_id_snapshot=env["dispatcher_id"],
        ))
        await s.commit()
    logs = await db_logs(env, t["id"])
    assert logs[-1].action_type is None            # 列值仍为 NULL（不回填）
    # 接口层兜底：由 action_for(from,to) 推导，前端不再自算流转规则
    r = await env["client"].get(f"/api/v1/tickets/{t['id']}/state-logs")
    entries = r.json()["data"]
    assert entries[-1]["action_type"] == "resolve"


# ── 13. allowed_actions / 能力位（Phase 6 后端唯一事实来源） ──


def _action_map(detail) -> dict:
    return {a["action"]: a for a in detail["allowed_actions"]}


async def test_allowed_actions_pending_admin(env):
    t = await env["create_ticket"]()
    d = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    acts = _action_map(d)
    assert set(acts) == {"dispatch", "return", "cancel"}
    assert acts["dispatch"]["target_state"] == "open"
    assert acts["dispatch"]["requires_reason"] is False
    assert acts["dispatch"]["requires_owner"] is True
    assert acts["dispatch"]["label"] == "分派"
    assert acts["return"]["target_state"] == "returned"
    assert acts["return"]["requires_reason"] is True   # pending→returned 必填原因
    assert acts["cancel"]["requires_reason"] is True
    assert d["is_terminal"] is False
    assert all(a["label"] for a in d["allowed_actions"])


async def test_allowed_actions_open_owner_and_capabilities(env):
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    with as_user(env["handler_id"], "agent"):
        d = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    acts = _action_map(d)
    # 当前处理人：可处理/暂缓/打回；撤销只给创建者 → 不出现
    assert set(acts) == {"resolve", "return", "hold"}
    assert acts["resolve"]["requires_reason"] is False
    assert acts["hold"]["requires_reason"] is True
    assert acts["return"]["requires_reason"] is True
    # 文章能力位（owner 身份）
    assert d["can_reply"] is True
    assert d["can_addition"] is True
    assert d["can_remind"] is True

    # 非 owner（admin 本人不是处理人）看不到处理说明能力
    d_admin = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    assert d_admin["can_reply"] is False
    assert d_admin["can_addition"] is True


async def test_allowed_actions_terminal_empty(env):
    t = await env["create_ticket"]()
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "cancelled", "reason": "关闭"})
    assert r.status_code == 200
    d = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    assert d["allowed_actions"] == []
    assert d["is_terminal"] is True
    assert d["can_reply"] is False and d["can_addition"] is False and d["can_remind"] is False


async def test_allowed_actions_exclude_unpermitted_and_api_rejects(env):
    """没出现在 allowed_actions 的动作，直接调 API 也会被拒（同一份矩阵）。"""
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        outsider = User(username="tb-outsider2", name="无关客服2", password_hash="x", role="agent")
        s.add(outsider)
        await s.commit()
        await s.refresh(outsider)
        oid, orole, ogid = outsider.id, outsider.role, outsider.group_id

    t = await env["create_ticket"]()
    with as_user(oid, orole, ogid):
        d = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
        assert d["allowed_actions"] == []          # 既非创建者也非对接人
        r = await env["client"].patch(
            f"/api/v1/tickets/{t['id']}",
            json={"state": "open", "owner_id": env["handler_id"]},
        )
    assert r.status_code == 403                    # 不可绕过
    tk = await db_ticket(env, t["id"])
    assert tk.state == "pending"


async def test_allowed_action_executes_successfully(env):
    """列表里的动作按其 target_state/requires_* 调 API 必然成功。"""
    t = await env["create_ticket"]()
    d = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    acts = _action_map(d)
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": acts["dispatch"]["target_state"],
        "owner_id": env["handler_id"],             # requires_owner
    })
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "open"

    with as_user(env["handler_id"], "agent"):
        d2 = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    acts2 = _action_map(d2)
    # requires_reason 的动作不带 reason 必须 400，带 reason 才 200
    r_bad = await env["client"].patch(
        f"/api/v1/tickets/{t['id']}", json={"state": acts2["hold"]["target_state"]}
    )
    assert r_bad.status_code == 400
    r_ok = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": acts2["hold"]["target_state"], "reason": "等待备件"})
    assert r_ok.status_code == 200


async def test_allowed_actions_resolved_dedupes_rewritten_on_hold(env):
    """resolved 的候选里 on_hold 被业务约束改写为 open：去重后只剩 archive/reopen。"""
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    await env["resolve"](t["id"])
    d = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    acts = _action_map(d)
    assert set(acts) == {"archive", "reopen"}
    assert acts["reopen"]["target_state"] == "open"
    assert acts["archive"]["requires_reason"] is False
    assert acts["reopen"]["requires_reason"] is True   # resolved→open 必填原因


async def test_remind_capability_once_only(env):
    t = await env["create_ticket"]()
    d = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    assert d["can_remind"] is True
    r = await env["client"].post(
        f"/api/v1/tickets/{t['id']}/articles",
        data={"type": "reminder", "body": "请尽快处理"},
    )
    assert r.status_code == 201, r.text
    d2 = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    assert d2["can_remind"] is False                  # 生命周期只能催办一次
    r2 = await env["client"].post(
        f"/api/v1/tickets/{t['id']}/articles",
        data={"type": "reminder", "body": "再催一次"},
    )
    assert r2.status_code == 422


# ── 14. 客户回访闭环（Phase 8） ─────────────────────────────


async def test_callback_details_roundtrip(env):
    """callback_details 端到端：PATCH 写入 → 详情/列表读取（不依赖状态流转）。"""
    t = await env["create_ticket"]()
    detail_text = "客户反馈：更换的模块仍偶发重启，已记录复现步骤与日志"
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "is_callbacked": True,
        "callback_required": True,
        "callback_details": detail_text,
    })
    assert r.status_code == 200, r.text
    assert r.json()["callback_details"] == detail_text
    d = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    assert d["callback_details"] == detail_text
    tk = await db_ticket(env, t["id"])
    assert tk.callback_details == detail_text       # 真正落库


async def test_dissatisfied_cannot_archive(env):
    """satisfaction=dissatisfied 不能直接归档：动作不下发 + 执行被 422 拦截。"""
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    await env["resolve"](t["id"])

    # 回访结果：不满意（带不满意原因）
    r1 = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "is_callbacked": True, "callback_required": True,
        "satisfaction": "dissatisfied",
        "callback_details": "重启问题仍未解决，客户要求再次上门",
    })
    assert r1.status_code == 200, r1.text

    # 详情：archive 动作不再下发，reopen 仍在（正确出口是退回重开）
    d = (await env["client"].get(f"/api/v1/tickets/{t['id']}")).json()
    acts = _action_map(d)
    assert "archive" not in acts, "不满意工单不应下发归档动作"
    assert "reopen" in acts

    # 直接调归档（绕过 UI）→ 422，状态与日志不变
    before = len(await db_logs(env, t["id"]))
    r2 = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "archived"})
    assert r2.status_code == 422, r2.text
    assert "不满意" in r2.text
    tk = await db_ticket(env, t["id"])
    assert tk.state == "resolved"
    assert len(await db_logs(env, t["id"])) == before

    # 同请求内 state+满意度一起发也不能绕过（闭环字段先于流转应用）
    t2 = await env["create_ticket"]()
    await env["dispatch"](t2["id"], env["handler_id"])
    await env["resolve"](t2["id"])
    r3 = await env["client"].patch(f"/api/v1/tickets/{t2['id']}", json={
        "state": "archived", "is_callbacked": True, "satisfaction": "dissatisfied",
    })
    assert r3.status_code == 422, r3.text
    assert (await db_ticket(env, t2["id"])).state == "resolved"

    # 批量归档同样被拦截（执行入口同源）
    r4 = await env["client"].post("/api/v1/tickets/batch-update", json={
        "ticket_ids": [t["id"]], "updates": {"state": "archived"},
    })
    assert r4.status_code == 422, r4.status_code
    assert (await db_ticket(env, t["id"])).state == "resolved"


async def test_satisfied_can_archive_with_details(env):
    """满意（或未评价）可正常归档，回访详情保留。"""
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    await env["resolve"](t["id"])
    r = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "archived",
        "is_callbacked": True, "callback_required": True,
        "satisfaction": "satisfied",
        "callback_details": "回访确认已解决，客户认可",
        "archive_notes": "闭环归档",
    })
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "archived"
    assert d["satisfaction"] == "satisfied"
    assert d["callback_details"] == "回访确认已解决，客户认可"
    assert d["archive_notes"] == "闭环归档"


async def test_no_callback_clears_satisfaction_and_can_archive(env):
    """既有回访语义（保留）：callback_required=false 清空满意度 → 可归档。

    已知绕过点（记录在案，Phase 9 报告中说明）：一张"不满意"的工单通过
    同请求改 callback_required=false 会先清空满意度，从而绕过不满意拦截。
    这是既有"无需回访即清空满意度"的回访语义，本次改造不改变它。
    """
    t = await env["create_ticket"]()
    await env["dispatch"](t["id"], env["handler_id"])
    await env["resolve"](t["id"])
    r1 = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "is_callbacked": True, "satisfaction": "dissatisfied",
    })
    assert r1.status_code == 200, r1.text
    r2 = await env["client"].patch(f"/api/v1/tickets/{t['id']}", json={
        "state": "archived", "callback_required": False,
    })
    assert r2.status_code == 200, r2.text
    d = r2.json()
    assert d["state"] == "archived"
    assert d["satisfaction"] is None
    assert d["is_callbacked"] is False
