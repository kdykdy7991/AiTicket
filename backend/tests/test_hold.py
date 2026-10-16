"""暂缓处理（on_hold）：processing 下的领域动作，不涉及任何 SLA 语义。

模型：
    processing ──hold──▶ on_hold ──resume──▶ processing

- 不新增 Node、不新增审批流；on_hold 期间 NodeContext 仍按 processing 解释；
- 暂缓原因 → TicketStateLog.reason（必填）；
- 预计恢复时间 → Ticket.hold_until（必填、必须晚于当前时间、不是 deadline）；
- 本期不为暂缓创建 TicketNodeSubmission，也不建 FormBinding；
- 到期只发一次钉钉提醒，不自动 resume / resolve / transfer / upgrade。
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup
from app.models.node_form import TicketNodeSubmission
from app.models.notification import DingtalkNotification
from app.models.ticket import Ticket, TicketStateLog
from app.models.user import User
from app.core.config import settings
from app.services import notification as notification_module
from app.services.sla_scanner import scan_hold_expiries
from test_refine import set_existing_open_ticket
from test_transfer import tenv
from test_workflow_regression import as_user

FUTURE = (datetime.now(timezone.utc) + timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
PAST = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")

LEAF = 2299        # 单步链：处理即链末步
FEEDBACK = 2298    # 两步链，第二步是售后致电反馈
JUDGE = 2297       # 判断节点（有下级），用于验证 triage 不能暂缓
JUDGE_CHILD = 2296


def factory_of(env):
    return async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)


async def opened(env, category_id=LEAF):
    """分派后走到 open 的处理中工单，返回 (工单 dict, owner_id)。"""
    t = await env["create_ticket"](category_id=category_id)
    owner_id = env["platform_user"]
    t = await env["patch"](t["id"], {"state": "open", "owner_id": owner_id})
    return t, owner_id


def hold_payload(**overrides):
    body = {"state": "on_hold", "reason": "等待客户提供登录日志", "hold_until": FUTURE}
    body.update(overrides)
    return body


async def ensure_triage_node(env):
    """造一个「有下级 + 链首=平台运维组」的判断节点。"""
    factory = factory_of(env)
    async with factory() as s:
        now = datetime.now(timezone.utc)
        for cid, parent, name in ((JUDGE, None, "暂缓判断父"), (JUDGE_CHILD, JUDGE, "暂缓判断子")):
            if await s.get(TicketCategory, cid) is None:
                s.add(TicketCategory(id=cid, parent_id=parent, name=name, level=1,
                                     sort_order=1, is_active=True,
                                     created_at=now, updated_at=now))
        for cid in (JUDGE, JUDGE_CHILD):
            if (await s.execute(select(DispatchChain).where(
                    DispatchChain.category_id == cid))).scalar_one_or_none() is None:
                s.add(DispatchChain(category_id=cid,
                                    steps=[{"order": 1, "department_code": "平台运维组"}]))
        await s.commit()


async def set_hold_state(env, tid, hold_until: datetime):
    """直接把工单置为 on_hold 并设定预计恢复时间（绕过时间校验，便于测提醒）。"""
    factory = factory_of(env)
    async with factory() as s:
        ticket = await s.get(Ticket, tid)
        ticket.state = "on_hold"
        ticket.hold_until = hold_until
        await s.commit()


# ── 1-5. 权限 ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_owner_can_hold_and_non_owner_cannot(tenv):
    t, owner_id = await opened(tenv)
    with as_user(owner_id, "handler"):
        d = (await tenv["client"].get("/api/v1/tickets/" + str(t["id"]))).json()
    assert "hold" in {a["action"] for a in d["allowed_actions"]}
    assert d["allowed_actions"] and all(a["label"] for a in d["allowed_actions"])

    r = await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]), json=hold_payload())
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "on_hold"

    t2, _ = await opened(tenv)
    with as_user(tenv["aftersale_user"], "handler"):
        denied = await tenv["client"].patch("/api/v1/tickets/" + str(t2["id"]),
                                           json=hold_payload())
    assert denied.status_code == 403
    assert (await tenv["get"](t2["id"]))["state"] == "open"


@pytest.mark.asyncio
async def test_admin_keeps_existing_permission(tenv):
    t, _ = await opened(tenv)
    r = await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]), json=hold_payload())
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "on_hold"


@pytest.mark.asyncio
async def test_triage_cannot_hold(tenv):
    await ensure_triage_node(tenv)
    t = await tenv["create_ticket"](category_id=JUDGE)
    detail = (await tenv["client"].get("/api/v1/tickets/" + str(t["id"]))).json()
    assert detail["node_context"]["node_type"] == "triage"
    assert "hold" not in {a["action"] for a in detail["allowed_actions"]}
    # 判断节点无法分派；用既有辅助构造「open 状态下的判断节点」，
    # 由 NodeContext 明确拦截暂缓（admin 也一样）
    await set_existing_open_ticket(tenv, t["id"])
    with as_user(tenv["platform_user"], "handler"):
        denied = await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]),
                                           json=hold_payload())
    assert denied.status_code == 422
    assert "分诊" in denied.text or "细化" in denied.text
    assert (await tenv["get"](t["id"]))["state"] == "open"


@pytest.mark.asyncio
async def test_phone_feedback_cannot_hold(tenv):
    t, owner_id = await opened(tenv, FEEDBACK)
    with as_user(owner_id, "handler"):
        r = await tenv["client"].post("/api/v1/tickets/" + str(t["id"]) + "/articles",
                                     data={"type": "reply", "body": "平台侧处理完成"})
    assert r.status_code == 201, r.text
    after = await tenv["get"](t["id"])
    assert after["node_context"]["node_type"] == "phone_feedback"
    await tenv["patch"](t["id"], {"state": "open", "owner_id": tenv["aftersale_user"]})
    with as_user(tenv["aftersale_user"], "handler"):
        detail = (await tenv["client"].get("/api/v1/tickets/" + str(t["id"]))).json()
    assert "hold" not in {a["action"] for a in detail["allowed_actions"]}
    with as_user(tenv["aftersale_user"], "handler"):
        denied = await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]),
                                           json=hold_payload())
    assert denied.status_code == 422


# ── 6-9. 校验 ───────────────────────────────────────────


@pytest.mark.asyncio
async def test_hold_validation(tenv):
    t, _ = await opened(tenv)
    path = "/api/v1/tickets/" + str(t["id"])
    for bad_reason in ("", "   ", None):
        assert (await tenv["client"].patch(
            path, json=hold_payload(reason=bad_reason))).status_code == 400, bad_reason
    # 预计恢复时间缺失 / 空串
    assert (await tenv["client"].patch(path, json=hold_payload(hold_until=None))).status_code == 422
    assert (await tenv["client"].patch(path, json=hold_payload(hold_until=""))).status_code == 422
    # 非法格式 → 明确 4xx，不是 500
    for bad in ("tomorrow", "2026/10/20", "not-a-date", "2026-13-45T99:99"):
        r = await tenv["client"].patch(path, json=hold_payload(hold_until=bad))
        assert r.status_code == 422, bad
    # 过去时间
    assert (await tenv["client"].patch(path, json=hold_payload(hold_until=PAST))).status_code == 422
    assert (await tenv["get"](t["id"]))["state"] == "open"


# ── 10-14. 成功暂缓后的事实保持 ──────────────────────────


@pytest.mark.asyncio
async def test_successful_hold_keeps_routing_facts(tenv):
    t, _ = await opened(tenv)
    before = await tenv["get"](t["id"])
    r = await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]), json=hold_payload())
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "on_hold"
    assert d["hold_until"] is not None
    assert d["category_id"] == before["category_id"]
    assert d["skill_group_id"] == before["skill_group_id"]
    assert d["owner_id"] == before["owner_id"]
    assert d["dispatch_step_index"] == before["dispatch_step_index"]
    assert d["dispatch_chain_steps"] == before["dispatch_chain_steps"]
    assert d["dispatcher_id"] == before["dispatcher_id"]
    # on_hold 期间 NodeContext 仍按 processing 解释
    detail = (await tenv["client"].get("/api/v1/tickets/" + str(t["id"]))).json()
    assert detail["node_context"]["node_type"] == "processing"
    assert detail["node_context"]["dispatch_step_index"] == before["dispatch_step_index"]
    # 暂缓原因落在 Flow Log，不新增 Ticket 列
    factory = factory_of(tenv)
    async with factory() as s:
        logs = (await s.execute(select(TicketStateLog).where(
            TicketStateLog.ticket_id == t["id"],
            TicketStateLog.action_type == "hold"))).scalars().all()
        assert len(logs) == 1 and logs[0].reason == "等待客户提供登录日志"
        tk = await s.get(Ticket, t["id"])
        assert tk.hold_reminded_at is None
        # 本期不为暂缓创建 Submission
        assert not (await s.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == t["id"]))).scalars().all()


# ── 15. 详情 API 返回 hold_until ─────────────────────────


@pytest.mark.asyncio
async def test_detail_returns_hold_until(tenv):
    t, _ = await opened(tenv)
    r = await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]), json=hold_payload())
    assert r.json()["hold_until"] is not None
    d = (await tenv["client"].get("/api/v1/tickets/" + str(t["id"]))).json()
    assert d["hold_until"] is not None
    assert d["state"] == "on_hold"


# ── 16-20. 提醒 scanner ─────────────────────────────────


@pytest.mark.asyncio
async def test_reminder_scanner(tenv, monkeypatch):
    sent: list[dict] = []

    async def fake_send(webhook_url, content, at_mobiles=None):
        sent.append({"webhook": webhook_url, "content": content, "at": at_mobiles})
        return notification_module.SendResult(True)

    monkeypatch.setattr(notification_module, "send_dingtalk_text", fake_send)
    monkeypatch.setattr(settings, "DINGTALK_NOTIFICATION_ENABLED", True)
    factory = factory_of(tenv)
    t, owner_id = await opened(tenv)

    # webhook 配在责任部门（技能组）上；处理人配手机号
    async with factory() as s:
        sg = (await s.execute(select(SkillGroup).where(
            SkillGroup.name == "平台运维组"))).scalar_one()
        sg.dingtalk_webhook_url = "https://oapi.dingtalk.com/robot/send?token=x"
        person = await s.get(User, owner_id)
        person.phone = "13800138000"
        await s.commit()

    now = datetime.now(timezone.utc)

    # 16) 未到时间不提醒
    await set_hold_state(tenv, t["id"], now + timedelta(days=1))
    assert await scan_hold_expiries(factory) == {"hold_expiry_reminded": 0}
    assert sent == []

    # 17) 时间到达 → 只提醒一次；18) 部门机器人 + @owner；19) 下一轮不重复
    await set_hold_state(tenv, t["id"], now - timedelta(minutes=1))
    assert await scan_hold_expiries(factory) == {"hold_expiry_reminded": 1}
    assert len(sent) == 1
    assert sent[0]["webhook"] == "https://oapi.dingtalk.com/robot/send?token=x"
    assert sent[0]["at"] == ["13800138000"]
    body = sent[0]["content"]
    for fragment in ("工单编号", "暂缓原因", "预计恢复时间", "当前处理人",
                     "请确认是否恢复处理"):
        assert fragment in body, fragment
    assert "超时" not in body and "SLA" not in body
    assert await scan_hold_expiries(factory) == {"hold_expiry_reminded": 0}
    assert len(sent) == 1

    # 通知落库
    async with factory() as s:
        records = (await s.execute(select(DingtalkNotification).where(
            DingtalkNotification.ticket_id == t["id"],
            DingtalkNotification.type == "hold_expiry"))).scalars().all()
        assert len(records) == 1 and records[0].success is True

    # 20) 不自动变化：状态仍是 on_hold，SLA 字段未被触碰
    d = (await tenv["client"].get("/api/v1/tickets/" + str(t["id"]))).json()
    assert d["state"] == "on_hold"
    assert d["sla_solution_breached"] is False
    assert d["solution_deadline"] is None


# ── 21-24. 恢复处理 ─────────────────────────────────────


@pytest.mark.asyncio
async def test_resume_returns_to_same_node_and_clears_hold(tenv):
    t, _ = await opened(tenv)
    before = await tenv["get"](t["id"])
    await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]), json=hold_payload())
    assert (await tenv["get"](t["id"]))["state"] == "on_hold"

    # 恢复仍需 reason（现有行为，本轮不改）
    assert (await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]),
                                       json={"state": "open"})).status_code == 400
    r = await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]),
                                   json={"state": "open", "reason": "客户已提供日志"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["state"] == "open"
    assert d["hold_until"] is None
    # 路由事实全部保持
    assert d["category_id"] == before["category_id"]
    assert d["skill_group_id"] == before["skill_group_id"]
    assert d["owner_id"] == before["owner_id"]
    assert d["dispatch_step_index"] == before["dispatch_step_index"]
    assert d["dispatch_chain_steps"] == before["dispatch_chain_steps"]
    detail = (await tenv["client"].get("/api/v1/tickets/" + str(t["id"]))).json()
    assert detail["node_context"]["node_type"] == "processing"
    factory = factory_of(tenv)
    async with factory() as s:
        log = (await s.execute(select(TicketStateLog).where(
            TicketStateLog.ticket_id == t["id"]).order_by(
            TicketStateLog.id.desc()).limit(1))).scalar_one()
        assert log.action_type == "resume"
        tk = await s.get(Ticket, t["id"])
        assert tk.hold_until is None and tk.hold_reminded_at is None


# ── 8. 新一轮暂缓 ───────────────────────────────────────


@pytest.mark.asyncio
async def test_rehold_starts_a_new_reminder_round(tenv, monkeypatch):
    sent: list[dict] = []

    async def fake_send(webhook_url, content, at_mobiles=None):
        sent.append({"content": content})
        return notification_module.SendResult(True)

    monkeypatch.setattr(notification_module, "send_dingtalk_text", fake_send)
    monkeypatch.setattr(settings, "DINGTALK_NOTIFICATION_ENABLED", True)
    factory = factory_of(tenv)
    t, owner_id = await opened(tenv)
    async with factory() as s:
        sg = (await s.execute(select(SkillGroup).where(
            SkillGroup.name == "平台运维组"))).scalar_one()
        sg.dingtalk_webhook_url = "https://oapi.dingtalk.com/robot/send?token=x"
        (await s.get(User, owner_id)).phone = "13800138000"
        await s.commit()
    path = "/api/v1/tickets/" + str(t["id"])
    later = (datetime.now(timezone.utc) + timedelta(days=3)).strftime("%Y-%m-%dT%H:%M:%S")

    assert (await tenv["client"].patch(path, json=hold_payload(hold_until=FUTURE))).status_code == 200
    await tenv["client"].patch(path, json={"state": "open", "reason": "客户已提供日志"})
    assert (await tenv["client"].patch(path, json=hold_payload(
        reason="等待第三方接口人回复", hold_until=later))).status_code == 200
    d = (await tenv["client"].get(path)).json()
    assert d["state"] == "on_hold"
    # resume 已清空 hold_reminded_at → 新一轮可以再提醒一次
    async with factory() as s:
        assert (await s.get(Ticket, t["id"])).hold_reminded_at is None
    await set_hold_state(tenv, t["id"], datetime.now(timezone.utc) - timedelta(minutes=1))
    assert await scan_hold_expiries(factory) == {"hold_expiry_reminded": 1}
    assert len(sent) == 1
    assert "等待第三方接口人回复" in sent[0]["content"]

    # on_hold → on_hold 不被支持：必须先 resume 再 hold
    assert (await tenv["client"].patch(path, json=hold_payload(
        reason="直接改时间", hold_until=later))).status_code == 422


# ── 26. 不触发 SLA ──────────────────────────────────────


@pytest.mark.asyncio
async def test_hold_touches_no_sla_fields(tenv):
    t, _ = await opened(tenv)
    before = await tenv["get"](t["id"])
    r = await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]), json=hold_payload())
    d = r.json()
    assert d["solution_deadline"] == before["solution_deadline"]
    assert d["sla_solution_breached"] == before["sla_solution_breached"]
    assert d["solved_at"] == before["solved_at"]
    await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]),
                               json={"state": "open", "reason": "继续处理"})
    after = await tenv["get"](t["id"])
    assert after["solution_deadline"] == before["solution_deadline"]
    assert after["sla_solution_breached"] == before["sla_solution_breached"]


# ── 10. on_hold → resolved 核验 ──────────────────────────


@pytest.mark.asyncio
async def test_on_hold_to_resolved_still_supported_but_not_the_main_flow(tenv):
    """核验结果：on_hold→resolved 边保留（PRD「人工确认」），但非本轮主流程。

    - 链末步：状态机仍允许（admin / owner），按钮由前端按主流程隐藏；
    - 中间步骤：仍被「须先恢复处理」拦截；
    - 没有任何前端入口直接走这条路（前端在 on_hold 时隐藏完成表单）。
    """
    # 链末步：边仍然有效
    t, _ = await opened(tenv)
    await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]), json=hold_payload())
    r = await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]),
                                   json={"state": "resolved", "reason": "暂缓期间已确认处理完成"})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "resolved"

    # 中间步骤：被既有规则拦截
    t2, owner = await opened(tenv, FEEDBACK)
    await tenv["client"].patch("/api/v1/tickets/" + str(t2["id"]), json=hold_payload())
    with as_user(owner, "handler"):
        denied = await tenv["client"].patch("/api/v1/tickets/" + str(t2["id"]),
                                           json={"state": "resolved", "reason": "想直接办结"})
    assert denied.status_code == 422
    assert "恢复处理" in denied.text


# ── 外部通知总开关 ───────────────────────────────────────


@pytest.mark.asyncio
async def test_notification_switch_defaults_to_off(tenv):
    """默认配置下钉钉外部通知总开关为 false（未显式打开时）。"""
    assert settings.DINGTALK_NOTIFICATION_ENABLED is False


@pytest.mark.asyncio
async def test_switch_off_means_no_scan_no_send_no_write(tenv, monkeypatch):
    """开关关闭：不扫描、不发送、不写 hold_reminded_at、不建 Notification。

    暂缓主流程不受影响：工单继续保持 on_hold，由处理人 resume。
    """
    monkeypatch.setattr(settings, "DINGTALK_NOTIFICATION_ENABLED", False)
    calls: list[dict] = []

    async def spy_send(webhook_url, content, at_mobiles=None):
        calls.append({"webhook": webhook_url})
        return notification_module.SendResult(True)

    monkeypatch.setattr(notification_module, "send_dingtalk_text", spy_send)

    factory = factory_of(tenv)
    t, _ = await opened(tenv)
    await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]), json=hold_payload())
    # 直接把预计恢复时间改到过去，模拟已到期（绕过建单时的时间校验）
    await set_hold_state(tenv, t["id"], datetime.now(timezone.utc) - timedelta(minutes=1))

    assert await scan_hold_expiries(factory) == {"hold_expiry_reminded": 0}
    assert calls == [], "开关关闭时不得发送任何 webhook"
    async with factory() as s:
        tk = await s.get(Ticket, t["id"])
        assert tk.hold_reminded_at is None, "未真正发送提醒不得写 hold_reminded_at"
        assert not (await s.execute(select(DingtalkNotification).where(
            DingtalkNotification.ticket_id == t["id"],
            DingtalkNotification.type == "hold_expiry"))).scalars().all()
    # 主流程不受影响
    assert (await tenv["get"](t["id"]))["state"] == "on_hold"
    r = await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]),
                                   json={"state": "open", "reason": "继续处理"})
    assert r.status_code == 200, r.text


@pytest.mark.asyncio
async def test_switch_on_but_send_failed_keeps_reminded_at_null(tenv, monkeypatch):
    """开关开启 + 发送失败：hold_reminded_at 保持 NULL，允许下一轮重试。"""
    monkeypatch.setattr(settings, "DINGTALK_NOTIFICATION_ENABLED", True)
    attempts: list[str] = []

    async def failing_send(webhook_url, content, at_mobiles=None):
        attempts.append(webhook_url)
        return notification_module.SendResult(False, "钉钉返回未知错误")

    monkeypatch.setattr(notification_module, "send_dingtalk_text", failing_send)
    factory = factory_of(tenv)
    t, _ = await opened(tenv)
    async with factory() as s:
        sg = (await s.execute(select(SkillGroup).where(
            SkillGroup.name == "平台运维组"))).scalar_one()
        sg.dingtalk_webhook_url = "https://oapi.dingtalk.com/robot/send?token=x"
        await s.commit()
    await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]), json=hold_payload())
    await set_hold_state(tenv, t["id"], datetime.now(timezone.utc) - timedelta(minutes=1))

    # 两轮都不成功 → 都不落 hold_reminded_at，且确实重试了
    assert await scan_hold_expiries(factory) == {"hold_expiry_reminded": 0}
    assert await scan_hold_expiries(factory) == {"hold_expiry_reminded": 0}
    assert len(attempts) == 2
    async with factory() as s:
        assert (await s.get(Ticket, t["id"])).hold_reminded_at is None
        records = (await s.execute(select(DingtalkNotification).where(
            DingtalkNotification.ticket_id == t["id"],
            DingtalkNotification.type == "hold_expiry"))).scalars().all()
        assert len(records) == 2 and all(r.success is False for r in records)
    assert (await tenv["get"](t["id"]))["state"] == "on_hold"


@pytest.mark.asyncio
async def test_switch_on_success_writes_reminded_at_once(tenv, monkeypatch):
    """开关开启 + 发送成功：写 hold_reminded_at，且只成功提醒一次。"""
    monkeypatch.setattr(settings, "DINGTALK_NOTIFICATION_ENABLED", True)
    sent: list[str] = []

    async def ok_send(webhook_url, content, at_mobiles=None):
        sent.append(content)
        return notification_module.SendResult(True)

    monkeypatch.setattr(notification_module, "send_dingtalk_text", ok_send)
    factory = factory_of(tenv)
    t, _ = await opened(tenv)
    async with factory() as s:
        sg = (await s.execute(select(SkillGroup).where(
            SkillGroup.name == "平台运维组"))).scalar_one()
        sg.dingtalk_webhook_url = "https://oapi.dingtalk.com/robot/send?token=x"
        await s.commit()
    await tenv["client"].patch("/api/v1/tickets/" + str(t["id"]), json=hold_payload())
    await set_hold_state(tenv, t["id"], datetime.now(timezone.utc) - timedelta(minutes=1))

    assert await scan_hold_expiries(factory) == {"hold_expiry_reminded": 1}
    assert await scan_hold_expiries(factory) == {"hold_expiry_reminded": 0}
    assert len(sent) == 1
    async with factory() as s:
        assert (await s.get(Ticket, t["id"])).hold_reminded_at is not None
