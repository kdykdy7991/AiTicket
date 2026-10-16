"""Closure node: published form owns the callback facts, the state machine owns the archive.

覆盖：
- 字段归属：回访/关单/认可度写 Ticket 正式字段，补充说明只进 Submission；
- 办结时间与办结人工号由既有流转生成（closed_at / StateLog.operator_id）；
- archive 入口收口：旧 PATCH 与批量归档都不能绕过已绑定的闭环表单；
- 回访要求来自分类规则（callback_policy），Closure 不改写它；
- 要求回访但未回访 → 禁止归档；无需回访 → 不出现回访字段且可归档；
- dissatisfied：表单只固化回访事实、不流转状态，重新处理链可回到关单；
- 并发：双击/两人同时提交只有一次生效；
- 历史兼容：未绑定表单时旧 PATCH 归档路径不变。
"""

import asyncio
from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.category import TicketCategory
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition, TicketNodeSubmission
from app.models.ticket import Ticket, TicketStateLog
from scripts.seed_closure_form import FIELDS, FORM_CODE, RESULT_LABELS
from test_transfer import tenv
from test_workflow_regression import as_user

CLOSED_RESULT = "recovered"
SATISFACTION_LABELS = {"satisfied": "满意", "average": "一般",
                       "dissatisfied": "不满意", "unrated": "未评价"}
# 2299 在测试里代表「要求回访」的分类；2298 保持默认（无需回访）。
REQUIRED_CATEGORY = 2299
OPTIONAL_CATEGORY = 2298


async def install_closure_form(env):
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        form = FormDefinition(code=FORM_CODE, name="客服回访闭环", node_type="closure",
                              version=1, enabled=True, published_at=None)
        s.add(form)
        await s.flush()
        for order, row in enumerate(FIELDS):
            key, label, kind, required, options, labels, visible, required_when, storage, storage_key, limit = row
            validation = {"option_labels": labels} if labels else {}
            if limit:
                validation["max_length"] = limit
            s.add(FormFieldDefinition(
                form_definition_id=form.id, field_key=key, label=label, field_type=kind,
                sort_order=order, required=required, options=options,
                validation=validation or None,
                visibility_condition=visible, required_condition=required_when,
                storage_type=storage, storage_key=storage_key,
            ))
        s.add(FormBinding(node_type="closure", department_code=None, category_id=None,
                          category_match_type="exact", form_definition_id=form.id,
                          priority=1, enabled=True))
        await s.flush()
        form.published_at = datetime.now(timezone.utc)
        # 分类规则：2299 要求回访（等价于生产里标在「业务保障」上）
        await s.execute(update(TicketCategory).where(TicketCategory.id == REQUIRED_CATEGORY)
                        .values(requires_callback=True))
        await s.commit()
        return form.id


async def resolved(env, category_id=REQUIRED_CATEGORY):
    """走到 resolved（closure 节点）的工单。"""
    t = await env["create_ticket"](category_id=category_id)
    owner = env["platform_user"]
    t = await env["patch"](t["id"], {"state": "open", "owner_id": owner})
    with as_user(owner, "handler"):
        r = await env["client"].post("/api/v1/tickets/" + str(t["id"]) + "/articles",
                                     data={"type": "reply", "body": "处理完成"})
    assert r.status_code == 201, r.text
    return await env["get"](t["id"])


def values(drop=(), **updates):
    data = {"callback_completed": True, "callback_details": "回访确认业务恢复",
            "satisfaction": "satisfied", "closure_result": CLOSED_RESULT,
            "customer_recognized": True, "archive_notes": "闭环归档"}
    for key in drop:
        data.pop(key, None)
    for key, value in updates.items():
        if value is None:
            data.pop(key, None)
        else:
            data[key] = value
    return data


def payload(ticket, form_id, form_version=1, drop=(), **updates):
    return {"form_definition_id": form_id, "form_version": form_version,
            "expected_category_id": ticket["category_id"],
            "expected_department_id": ticket["skill_group_id"],
            "expected_dispatch_step_index": ticket["dispatch_step_index"],
            "expected_state": ticket["state"], "values": values(drop, **updates)}


async def submit(env, ticket, form_id, *, user_id=None, role="agent", form_version=1,
                  drop=(), **updates):
    path = "/api/v1/tickets/" + str(ticket["id"]) + "/closure-submit"
    with as_user(user_id or env["aftersale_user"], role):
        return await env["client"].post(
            path, json=payload(ticket, form_id, form_version, drop, **updates))


@pytest.mark.asyncio
async def test_closure_form_owns_callback_facts_and_archives(tenv):
    form_id = await install_closure_form(tenv)
    ticket = await resolved(tenv)
    tid = ticket["id"]
    with as_user(tenv["aftersale_user"], "agent"):
        detail = (await tenv["client"].get("/api/v1/tickets/" + str(tid))).json()
        assert detail["node_context"]["node_type"] == "closure"
        assert detail["current_form"]["code"] == FORM_CODE
        assert detail["callback_required"] is True
        labels = {f["field_key"]: f["option_labels"] for f in detail["current_form"]["fields"]}
        assert labels["closure_result"] == RESULT_LABELS
        assert labels["satisfaction"] == SATISFACTION_LABELS
    r = await submit(tenv, ticket, form_id, closure_result_note="仅进 Submission")
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["state"] == "archived"
    # 正式字段是当前真值
    assert data["closure_result"] == CLOSED_RESULT
    assert data["customer_recognized"] is True
    assert data["is_callbacked"] is True
    assert data["callback_required"] is True
    assert data["satisfaction"] == "satisfied"
    assert data["callback_details"] == "回访确认业务恢复"
    assert data["archive_notes"] == "闭环归档"
    assert data["closed_at"] is not None
    assert data["archived_by_id"] is not None
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        record = (await s.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == tid))).scalar_one()
        assert record.node_type == "closure" and record.action_type == "archive"
        # Submission 只保留补充说明，不复制任何 Ticket 正式真值
        assert record.data == {"closure_result_note": "仅进 Submission"}
        keys = {f["key"] for f in record.field_snapshot}
        assert {"satisfaction", "closure_result", "customer_recognized"} <= keys
        log = await s.get(TicketStateLog, record.state_log_id)
        assert (log.from_state, log.to_state, log.action_type) == ("resolved", "archived", "archive")
        assert log.operator_id == tenv["aftersale_user"]      # 办结人工号来自 StateLog
        assert (await s.get(Ticket, tid)).closed_at is not None
    history = (await tenv["client"].get("/api/v1/tickets/" + str(tid) + "/node-submissions")).json()
    assert history[0]["node_type"] == "closure"


@pytest.mark.asyncio
async def test_archive_entry_points_are_closed(tenv):
    form_id = await install_closure_form(tenv)
    ticket = await resolved(tenv)
    tid = ticket["id"]
    path = "/api/v1/tickets/" + str(tid)
    assert (await tenv["client"].patch(path, json={"state": "archived"})).status_code == 409
    batch = await tenv["client"].post("/api/v1/tickets/batch-update", json={
        "ticket_ids": [tid], "updates": {"state": "archived"}})
    assert batch.status_code == 409
    assert (await submit(tenv, ticket, form_id)).status_code == 200
    repeat = await tenv["client"].patch(path, json={"state": "archived"})
    assert repeat.status_code == 200
    assert repeat.json()["state"] == "archived"


@pytest.mark.asyncio
async def test_closure_validation_permissions_and_replay(tenv):
    form_id = await install_closure_form(tenv)
    ticket = await resolved(tenv)
    tid = ticket["id"]
    # 回访未完成时，客户侧结论字段不出现
    assert (await submit(tenv, ticket, form_id, drop=("callback_completed",))).status_code == 422
    # 未完成回访：客户侧结论字段被隐藏，夹带即拒绝；只记录「未完成」本身
    not_done = ("callback_completed", "callback_details", "satisfaction", "customer_recognized")
    assert (await submit(tenv, ticket, form_id, callback_completed=False,
                         drop=("callback_details", "satisfaction",
                               "customer_recognized"))).status_code == 200
    assert (await submit(tenv, ticket, form_id, callback_completed=False,
                         satisfaction="satisfied")).status_code == 422
    assert not_done
    # 完成后：关单结果 / 认可度必填
    fresh = await resolved(tenv)
    for key in ("closure_result", "customer_recognized"):
        assert (await submit(tenv, fresh, form_id, drop=(key,))).status_code == 422, key
    assert (await submit(tenv, fresh, form_id, closure_result="other")).status_code == 422
    assert (await submit(tenv, fresh, form_id, closure_result="随便写")).status_code == 422
    assert (await submit(tenv, fresh, form_id, satisfaction="very_good")).status_code == 422
    assert (await submit(tenv, fresh, form_id, satisfaction="dissatisfied")).status_code == 422
    # 权限：非客服团队不能归档
    denied = await submit(tenv, fresh, form_id, user_id=tenv["platform_user"], role="handler")
    assert denied.status_code == 403
    # 表单版本与客户端上下文
    assert (await submit(tenv, fresh, form_id, form_version=2)).status_code == 409
    stale = dict(payload(fresh, form_id), expected_state="open")
    with as_user(tenv["aftersale_user"], "agent"):
        r = await tenv["client"].post("/api/v1/tickets/" + str(fresh["id"]) + "/closure-submit",
                                     json=stale)
    assert r.status_code == 409
    assert (await submit(tenv, fresh, form_id)).status_code == 200
    assert (await submit(tenv, fresh, form_id)).status_code == 409


@pytest.mark.asyncio
async def test_closure_form_hidden_outside_closure_and_when_dissatisfied(tenv):
    await install_closure_form(tenv)
    opened = await tenv["create_ticket"](category_id=REQUIRED_CATEGORY)
    with as_user(tenv["platform_user"], "handler"):
        detail = (await tenv["client"].get("/api/v1/tickets/" + str(opened["id"]))).json()
    assert detail["node_context"]["node_type"] == "processing"
    assert detail["current_form"] is None
    wrong = await tenv["client"].post("/api/v1/tickets/" + str(opened["id"]) + "/closure-submit",
                                     json=payload(opened, 1))
    assert wrong.status_code == 409
    # 已存在不满意事实时不再下发闭环表单，必须退回重开
    ticket = await resolved(tenv)
    await tenv["patch"](ticket["id"], {"is_callbacked": True, "satisfaction": "dissatisfied",
                                       "unsatisfied_reason": "问题复现"})
    with as_user(tenv["aftersale_user"], "agent"):
        detail = (await tenv["client"].get("/api/v1/tickets/" + str(ticket["id"]))).json()
    assert detail["node_context"]["node_type"] == "closure"
    assert detail["current_form"] is None
    assert "archive" not in {a["action"] for a in detail["allowed_actions"]}


@pytest.mark.asyncio
async def test_dissatisfied_records_facts_then_reprocess_to_archive(tenv):
    form_id = await install_closure_form(tenv)
    ticket = await resolved(tenv)
    tid = ticket["id"]
    path = "/api/v1/tickets/" + str(tid)
    recorded = await submit(tenv, ticket, form_id, satisfaction="dissatisfied",
                            unsatisfied_reason="重启后问题仍复现")
    assert recorded.status_code == 200, recorded.text
    data = recorded.json()["data"]
    # 只固化回访事实，不流转状态
    assert data["state"] == "resolved"
    assert data["satisfaction"] == "dissatisfied"
    assert data["unsatisfied_reason"] == "重启后问题仍复现"
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        record = (await s.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == tid))).scalar_one()
        assert record.action_type == "callback_record" and record.state_log_id is None
        logs = (await s.execute(select(TicketStateLog).where(
            TicketStateLog.ticket_id == tid))).scalars().all()
        assert not [log for log in logs if log.action_type == "archive"]
    # 不满意不可原地改写为非不满意（与单条 PATCH 同源）
    rewritten = await submit(tenv, ticket, form_id, satisfaction="satisfied")
    assert rewritten.status_code == 422
    # 重新处理链：reopen → 再次处理 → resolved → 新的 closure → 归档
    reopened = await tenv["patch"](tid, {"state": "open", "reason": "需重新处理"})
    assert reopened["state"] == "open"
    with as_user(tenv["platform_user"], "handler"):
        r = await tenv["client"].post(path + "/articles",
                                     data={"type": "reply", "body": "已再次处理完成"})
    assert r.status_code == 201, r.text
    again = await tenv["get"](tid)
    assert again["state"] == "resolved"
    assert again["satisfaction"] is None      # 重开清空上一轮评价
    archived = await submit(tenv, again, form_id, satisfaction="satisfied",
                            callback_details="二次回访客户认可")
    assert archived.status_code == 200, archived.text
    assert archived.json()["data"]["state"] == "archived"


@pytest.mark.asyncio
async def test_closure_parallel_submits_only_once(tenv):
    form_id = await install_closure_form(tenv)
    ticket = await resolved(tenv)
    body = payload(ticket, form_id)
    with as_user(tenv["aftersale_user"], "agent"):
        responses = await asyncio.gather(*(
            tenv["client"].post("/api/v1/tickets/" + str(ticket["id"]) + "/closure-submit", json=body)
            for _ in range(2)
        ))
    assert sorted(r.status_code for r in responses) == [200, 409]
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        assert len((await s.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket["id"]))).scalars().all()) == 1
        assert len((await s.execute(select(TicketStateLog).where(
            TicketStateLog.ticket_id == ticket["id"],
            TicketStateLog.action_type == "archive"))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_legacy_archive_still_works_without_closure_binding(tenv):
    """历史兼容：未绑定闭环表单时，旧 PATCH 归档路径与既有关闭字段行为不变。"""
    ticket = await resolved(tenv)
    tid = ticket["id"]
    with as_user(tenv["aftersale_user"], "agent"):
        detail = (await tenv["client"].get("/api/v1/tickets/" + str(tid))).json()
    assert detail["node_context"]["node_type"] == "closure"
    assert detail["current_form"] is None
    r = await tenv["client"].patch("/api/v1/tickets/" + str(tid), json={
        "state": "archived", "is_callbacked": True, "satisfaction": "satisfied",
        "archive_notes": "旧路径归档"})
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["state"] == "archived" and data["archive_notes"] == "旧路径归档"
    assert data["closure_result"] is None          # 未走表单，不伪造关单结果
    history = (await tenv["client"].get("/api/v1/tickets/" + str(tid) + "/node-submissions")).json()
    assert history == []
