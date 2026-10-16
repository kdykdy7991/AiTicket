"""「是否需要回访」由分类规则决定，与「是否已完成回访」严格分离。

规则来源是 ticket_categories.requires_callback，语义为「自身或任一祖先为 True」。
业务代码不硬编码分类 ID，只读这一列。
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition, TicketNodeSubmission
from app.models.ticket import Ticket
from app.services.callback_policy import resolve_callback_required
from scripts.seed_closure_form import FIELDS, FORM_CODE
from test_transfer import tenv
from test_workflow_regression import as_user

# 一棵覆盖全部规则分支的分类树：
#   1000 咨询类            （其他一级 → 不要求）
#   2000 业务运营          （一级不标 → 由子级分别判断）
#     2001 套餐变更        （标 → 要求，后代继承）
#       2002 套餐变更子类  （继承 → 要求）
#     2003 其他运营        （不标 → 不要求）
#   3000 业务保障          （标 → 整个大类及其后代要求）
#     3001 应用平台        （继承 → 要求）
#       3002 核心网系统    （继承 → 要求）
TREE = [
    (1000, None, "咨询类"),
    (2000, None, "业务运营"),
    (2001, 2000, "套餐变更"),
    (2002, 2001, "套餐变更子类"),
    (2003, 2000, "其他运营"),
    (3000, None, "业务保障"),
    (3001, 3000, "应用平台"),
    (3002, 3001, "核心网系统"),
]
REQUIRED = {2001, 3000}
INHERITED = {2002, 3001, 3002}
# 叶子分类：建单可直接到达，也是闭环测试用的节点
REQUIRED_LEAF = 3002
OPTIONAL_LEAF = 2003
# 可分诊的判断节点（一级，链首=售后）
JUDGEMENT_ROOT = 2000


async def install_tree_and_form(env):
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        existing = set((await s.execute(select(TicketCategory.id))).scalars().all())
        for cid, parent, name in TREE:
            if cid not in existing:
                s.add(TicketCategory(id=cid, parent_id=parent, name=name, level=1,
                                     sort_order=1, is_active=True,
                                     requires_callback=cid in REQUIRED))
        # 每个分类都挂一条链，保证建单能落到对接人；判断节点由链首决定
        for cid, _parent, _name in TREE:
            if (await s.execute(select(DispatchChain).where(
                    DispatchChain.category_id == cid))).scalar_one_or_none() is None:
                s.add(DispatchChain(category_id=cid,
                                    steps=[{"order": 1, "department_code": "售后"}]))
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
        await s.commit()
        return form.id


def closure_values(**updates):
    data = {"callback_completed": True, "callback_details": "已回访",
            "satisfaction": "satisfied", "closure_result": "recovered",
            "customer_recognized": True}
    for key, value in updates.items():
        if value is None:
            data.pop(key, None)      # 隐藏字段必须整体不出现
        else:
            data[key] = value
    return data


def closure_payload(ticket, form_id, **updates):
    return {"form_definition_id": form_id, "form_version": 1,
            "expected_category_id": ticket["category_id"],
            "expected_department_id": ticket["skill_group_id"],
            "expected_dispatch_step_index": ticket["dispatch_step_index"],
            "expected_state": ticket["state"], "values": closure_values(**updates)}


async def resolve_ticket(env, tid):
    """分派给售后处理人并办结，走到 closure 节点。"""
    await env["patch"](tid, {"state": "open", "owner_id": env["aftersale_user"]})
    with as_user(env["aftersale_user"], "handler"):
        r = await env["client"].post("/api/v1/tickets/" + str(tid) + "/articles",
                                     data={"type": "reply", "body": "处理完成"})
    assert r.status_code == 201, r.text
    return (await env["client"].get("/api/v1/tickets/" + str(tid))).json()


@pytest.mark.asyncio
async def test_category_rule_derivation(tenv):
    await install_tree_and_form(tenv)
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        for cid, _parent, _name in TREE:
            expected = cid in REQUIRED or cid in INHERITED
            assert await resolve_callback_required(s, cid) is expected, cid
        assert await resolve_callback_required(s, None) is False


@pytest.mark.asyncio
async def test_ticket_flag_follows_category_at_creation(tenv):
    await install_tree_and_form(tenv)
    for cid, expected in ((1000, False), (2003, False), (2001, True), (2002, True),
                          (3000, True), (3002, True)):
        t = await tenv["create_ticket"](category_id=cid)
        detail = (await tenv["client"].get("/api/v1/tickets/" + str(t["id"]))).json()
        assert detail["callback_required"] is expected, (cid, detail["callback_required"])


@pytest.mark.asyncio
async def test_refine_recomputes_the_rule(tenv):
    """分诊细化改变分类：要求回访随新分类重算，不能只在建单时算一次。"""
    await install_tree_and_form(tenv)
    ticket = await tenv["create_ticket"](category_id=JUDGEMENT_ROOT)   # 一级不标 → 不要求
    tid = ticket["id"]
    detail = (await tenv["client"].get("/api/v1/tickets/" + str(tid))).json()
    assert detail["callback_required"] is False
    assert detail["node_context"]["node_type"] == "triage"
    # 细化到 套餐变更(2001) → 规则随之变为要求回访
    with as_user(tenv["aftersale_user"], "handler"):
        refined = await tenv["client"].post("/api/v1/tickets/" + str(tid) + "/refine",
                                           json={"category_id": 2001})
    assert refined.status_code == 200, refined.text
    after = (await tenv["client"].get("/api/v1/tickets/" + str(tid))).json()
    assert after["category_id"] == 2001
    assert after["callback_required"] is True


@pytest.mark.asyncio
async def test_required_but_not_callbacked_blocks_archive(tenv):
    form_id = await install_tree_and_form(tenv)
    ticket = await tenv["create_ticket"](category_id=REQUIRED_LEAF)
    tid = ticket["id"]
    detail = await resolve_ticket(tenv, tid)
    assert detail["state"] == "resolved"
    assert detail["callback_required"] is True and detail["is_callbacked"] is False
    with as_user(tenv["aftersale_user"], "agent"):
        view = (await tenv["client"].get("/api/v1/tickets/" + str(tid))).json()
    # 归档按钮不下发；闭环表单仍可用，因为要先记录回访事实
    assert "archive" not in {a["action"] for a in view["allowed_actions"]}
    assert view["current_form"]["code"] == FORM_CODE
    # 旧 PATCH / 批量归档都被闭环表单入口拦截（绑定生效后无旁路）
    assert (await tenv["client"].patch("/api/v1/tickets/" + str(tid),
                                       json={"state": "archived"})).status_code == 409
    batch = await tenv["client"].post("/api/v1/tickets/batch-update", json={
        "ticket_ids": [tid], "updates": {"state": "archived"}})
    assert batch.status_code == 409
    # 记录回访后一步闭环
    with as_user(tenv["aftersale_user"], "agent"):
        done = await tenv["client"].post("/api/v1/tickets/" + str(tid) + "/closure-submit",
                                         json=closure_payload(detail, form_id))
    assert done.status_code == 200, done.text
    assert done.json()["data"]["state"] == "archived"
    async with async_sessionmaker(tenv["engine"], class_=AsyncSession,
                                  expire_on_commit=False)() as s:
        record = (await s.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == tid))).scalar_one()
        assert record.action_type == "archive"
        saved = await s.get(Ticket, tid)
        assert saved.callback_required is True and saved.is_callbacked is True


@pytest.mark.asyncio
async def test_not_required_ticket_has_no_callback_fields_and_archives(tenv):
    form_id = await install_tree_and_form(tenv)
    ticket = await tenv["create_ticket"](category_id=OPTIONAL_LEAF)
    tid = ticket["id"]
    detail = await resolve_ticket(tenv, tid)
    with as_user(tenv["aftersale_user"], "agent"):
        view = (await tenv["client"].get("/api/v1/tickets/" + str(tid))).json()
    assert view["callback_required"] is False
    assert "archive" in {a["action"] for a in view["allowed_actions"]}
    visible = [f["field_key"] for f in view["current_form"]["fields"] if f["visible"]]
    assert visible == ["closure_result", "closure_result_note", "archive_notes"]
    with as_user(tenv["aftersale_user"], "agent"):
        done = await tenv["client"].post("/api/v1/tickets/" + str(tid) + "/closure-submit",
                                         json=closure_payload(detail, form_id,
                                                              callback_completed=None,
                                                              callback_details=None,
                                                              satisfaction=None,
                                                              customer_recognized=None))
    assert done.status_code == 200, done.text
    data = done.json()["data"]
    assert data["state"] == "archived"
    assert data["callback_required"] is False and data["is_callbacked"] is False


@pytest.mark.asyncio
async def test_precondition_blocks_archive_without_form_binding(tenv):
    """未绑定闭环表单时，归档前置条件本身仍要拦住「要求回访但未回访」。"""
    await install_tree_and_form(tenv)
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        await s.execute(update(FormBinding).where(FormBinding.node_type == "closure")
                        .values(enabled=False))
        await s.commit()
    ticket = await tenv["create_ticket"](category_id=REQUIRED_LEAF)
    tid = ticket["id"]
    await resolve_ticket(tenv, tid)
    with as_user(tenv["aftersale_user"], "agent"):
        view = (await tenv["client"].get("/api/v1/tickets/" + str(tid))).json()
    assert view["callback_required"] is True and view["is_callbacked"] is False
    assert "archive" not in {a["action"] for a in view["allowed_actions"]}
    assert (await tenv["client"].patch("/api/v1/tickets/" + str(tid),
                                       json={"state": "archived"})).status_code == 422
    # 同一请求里先补回访事实即可放行（字段先于流转应用）
    ok = await tenv["client"].patch("/api/v1/tickets/" + str(tid), json={
        "state": "archived", "is_callbacked": True, "satisfaction": "satisfied"})
    assert ok.status_code == 200, ok.text


@pytest.mark.asyncio
async def test_client_cannot_set_callback_required(tenv):
    form_id = await install_tree_and_form(tenv)
    ticket = await tenv["create_ticket"](category_id=REQUIRED_LEAF)
    tid = ticket["id"]
    detail = await resolve_ticket(tenv, tid)
    forged = closure_payload(detail, form_id)
    forged["values"]["callback_required"] = False
    with as_user(tenv["aftersale_user"], "agent"):
        r = await tenv["client"].post("/api/v1/tickets/" + str(tid) + "/closure-submit",
                                      json=forged)
    assert r.status_code == 422
    saved = (await tenv["client"].get("/api/v1/tickets/" + str(tid))).json()
    assert saved["callback_required"] is True
