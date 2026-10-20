"""Processing node form: one Article, one Submission and one domain transition."""

import asyncio
import json
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.node_form import FormBinding, FormDefinition, FormFieldDefinition, TicketNodeSubmission
from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.ticket import Article, ArticleAttachment, Ticket, TicketStateLog
from app.models.user import User
from scripts.seed_processing_form import FIELDS
from test_transfer import tenv
from test_refine import renv
from test_workflow_regression import as_user


async def install_form(env):
    factory = async_sessionmaker(env["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        form = FormDefinition(code="processing_v1", name="责任部门处理", node_type="processing",
                              version=1, enabled=True, published_at=None)
        s.add(form)
        await s.flush()
        for order, (key, label, kind, required, options, condition, storage, storage_key, limit) in enumerate(FIELDS):
            s.add(FormFieldDefinition(form_definition_id=form.id, field_key=key, label=label,
                field_type=kind, sort_order=order, required=required, options=options,
                validation={"max_length": limit} if limit else None,
                visibility_condition=condition, required_condition=condition if key == "long_term_plan" else None,
                storage_type=storage, storage_key=storage_key))
        s.add(FormBinding(node_type="processing", department_code=None, category_id=None,
                          category_match_type="exact", form_definition_id=form.id, priority=0, enabled=True))
        await s.flush()
        form.published_at = datetime.now(timezone.utc)
        await s.commit()
        return form.id


async def opened(env, category_id=2203):
    t = await env["create_ticket"](category_id=category_id)
    owner = env["platform_user"] if category_id in (2298, 2299) else env["aftersale_user"]
    t = await env["patch"](t["id"], {"state": "open", "owner_id": owner})
    return t, owner


def request(t, form_id, **updates):
    values = {"cause_category": "配置错误", "root_cause": "路由参数有误",
              "temporary_measure": "临时切换", "requires_long_term_action": False,
              "processing_opinion": "已处理并验证"}
    values.update(updates)
    return {"form_definition_id": form_id, "form_version": 1,
            "expected_category_id": t["category_id"],
            "expected_department_id": t["skill_group_id"],
            "expected_dispatch_step_index": t["dispatch_step_index"],
            "expected_state": "open", "values": values}


async def submit(env, t, form_id, user_id, *, files=None, **updates):
    with as_user(user_id, "handler"):
        return await env["client"].post(f"/api/v1/tickets/{t['id']}/node-submit",
            data={"payload": json.dumps(request(t, form_id, **updates))}, files=files or [])


@pytest.mark.asyncio
async def test_processing_form_mid_chain_article_submission_and_feedback(tenv, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    form_id = await install_form(tenv)
    t, owner = await opened(tenv, 2298)
    with as_user(owner, "handler"):
        detail = await tenv["get"](t["id"])
        assert detail["node_context"]["node_type"] == "processing"
        assert detail["current_form"]["form_definition_id"] == form_id
        assert detail["can_note"] is True and detail["can_reply"] is False
        note = await tenv["client"].post(f"/api/v1/tickets/{t['id']}/articles",
                                          data={"type": "note", "body": "正在排查"})
        assert note.status_code == 201, note.text
        assert (await tenv["get"](t["id"]))["state"] == "open"
        bypass = await tenv["client"].post(f"/api/v1/tickets/{t['id']}/articles",
                                            data={"type": "reply", "body": "绕过表单"})
        assert bypass.status_code == 409
    r = await submit(tenv, t, form_id, owner,
        files=[("attachments", ("proof.png", b"image-data", "image/png"))])
    assert r.status_code == 200, r.text
    d = r.json()["data"]
    assert d["state"] == "pending" and d["dispatch_step_index"] == 1
    assert d["skill_group_name"] == "售后"
    assert d["node_context"]["node_type"] == "phone_feedback"
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        submission = (await s.execute(select(TicketNodeSubmission).where(TicketNodeSubmission.ticket_id == t["id"]))).scalar_one()
        article = await s.get(Article, submission.article_id)
        attachments = (await s.execute(select(ArticleAttachment).where(ArticleAttachment.article_id == article.id))).scalars().all()
        ticket = await s.get(Ticket, t["id"])
        log = await s.get(TicketStateLog, submission.state_log_id)
        assert submission.data == {"cause_category": "配置错误", "temporary_measure": "临时切换",
                                   "requires_long_term_action": False}
        assert ticket.root_cause == "路由参数有误"
        assert ticket.solution is None and ticket.resolution is None
        assert article.body == "已处理并验证" and article.type == "reply"
        assert log.action_type == "transfer"
        assert len(attachments) == 1
    history = (await tenv["client"].get(f"/api/v1/tickets/{t['id']}/node-submissions")).json()
    assert history[0]["article_body"] == "已处理并验证"
    assert history[0]["attachments"][0]["filename"] == "proof.png"


@pytest.mark.asyncio
async def test_final_processing_resolves_and_validates_fields(tenv):
    form_id = await install_form(tenv)
    t, owner = await opened(tenv, 2299)
    with as_user(owner, "handler"):
        fields = (await tenv["client"].get(f"/api/v1/tickets/{t['id']}/current-form")).json()["fields"]
    assert {f["field_key"] for f in fields} >= {"cause_category", "root_cause", "temporary_measure", "long_term_plan", "processing_opinion"}
    for key in ("cause_category", "root_cause", "temporary_measure", "processing_opinion"):
        r = await submit(tenv, t, form_id, owner, **{key: ""})
        assert r.status_code == 422, (key, r.text)
    assert (await submit(tenv, t, form_id, owner, cause_category="随意输入")).status_code == 422
    assert (await submit(tenv, t, form_id, owner, requires_long_term_action=True)).status_code == 422
    r = await submit(tenv, t, form_id, owner, requires_long_term_action=True, long_term_plan="长期修复")
    assert r.status_code == 200, r.text
    assert r.json()["data"]["state"] == "resolved"
    assert (await tenv["client"].get(f"/api/v1/tickets/{t['id']}/node-submissions")).json()[0]["data"]["long_term_plan"] == "长期修复"


@pytest.mark.asyncio
async def test_processing_permissions_context_and_replay(tenv):
    form_id = await install_form(tenv)
    t, owner = await opened(tenv)
    assert (await tenv["client"].patch(f"/api/v1/tickets/{t['id']}", json={"state": "resolved"})).status_code == 409
    batch = await tenv["client"].post("/api/v1/tickets/batch-update", json={
        "ticket_ids": [t["id"]], "updates": {"state": "resolved"},
    })
    assert batch.status_code == 409
    assert (await submit(tenv, t, form_id, tenv["platform_user"])).status_code == 403
    r = await submit(tenv, t, form_id, owner)
    assert r.status_code == 200, r.text
    repeat = await submit(tenv, t, form_id, owner)
    assert repeat.status_code == 409


@pytest.mark.asyncio
async def test_processing_failure_rolls_back_article_submission_ticket_and_files(tenv, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    form_id = await install_form(tenv)
    t, owner = await opened(tenv)
    with patch("app.api.v1.tickets.apply_transition", side_effect=RuntimeError("injected")):
        with pytest.raises(RuntimeError, match="injected"):
            await submit(tenv, t, form_id, owner,
                files=[("attachments", ("proof.png", b"image-data", "image/png"))])
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        ticket = await s.get(Ticket, t["id"])
        assert ticket.root_cause is None and ticket.dispatch_step_index == 0 and ticket.state == "open"
        assert not (await s.execute(select(TicketNodeSubmission).where(TicketNodeSubmission.ticket_id == t["id"]))).scalars().all()
        assert not (await s.execute(select(Article).where(Article.ticket_id == t["id"]))).scalars().all()
        assert not (await s.execute(select(ArticleAttachment))).scalars().all()
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]


@pytest.mark.asyncio
async def test_parallel_processing_only_one_completion(tenv):
    form_id = await install_form(tenv)
    t, owner = await opened(tenv)
    with as_user(owner, "handler"):
        responses = await asyncio.gather(*(
            tenv["client"].post(f"/api/v1/tickets/{t['id']}/node-submit",
                data={"payload": json.dumps(request(t, form_id))}) for _ in range(2)
        ))
    assert sorted(r.status_code for r in responses) == [200, 409]
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        assert len((await s.execute(select(TicketNodeSubmission).where(TicketNodeSubmission.ticket_id == t["id"]))).scalars().all()) == 1
        assert len((await s.execute(select(Article).where(Article.ticket_id == t["id"], Article.type == "reply"))).scalars().all()) == 1


@pytest.mark.asyncio
async def test_phone_feedback_and_admin_wrong_node_rejected(tenv):
    form_id = await install_form(tenv)
    t, owner = await opened(tenv, 2298)
    assert (await submit(tenv, t, form_id, owner)).status_code == 200
    pending = await tenv["get"](t["id"])
    assert pending["node_context"]["node_type"] == "phone_feedback"
    await tenv["patch"](t["id"], {"state": "open", "owner_id": tenv["aftersale_user"]})
    feedback = await tenv["get"](t["id"])
    assert feedback["node_context"]["node_type"] == "phone_feedback"
    assert feedback["current_form"] is None
    wrong = await tenv["client"].post(f"/api/v1/tickets/{t['id']}/node-submit",
        data={"payload": json.dumps(request(feedback, form_id))})
    assert wrong.status_code == 409


@pytest.mark.asyncio
async def test_return_and_reopen_rederive_processing(tenv):
    form_id = await install_form(tenv)
    t, owner = await opened(tenv)
    assert (await submit(tenv, t, form_id, owner)).status_code == 200
    returned = await tenv["patch"](t["id"], {"state": "returned", "reason": "需原部门补充"})
    assert returned["state"] == "open"
    with as_user(owner, "handler"):
        detail = await tenv["get"](t["id"])
        assert detail["node_context"]["node_type"] == "processing"
        assert detail["current_form"]["form_definition_id"] == form_id
    final, final_owner = await opened(tenv, 2299)
    assert (await submit(tenv, final, form_id, final_owner)).status_code == 200
    reopened = await tenv["patch"](final["id"], {"state": "open", "reason": "复查"})
    assert reopened["state"] == "open"
    with as_user(final_owner, "handler"):
        assert (await tenv["get"](final["id"]))["node_context"]["node_type"] == "processing"


@pytest.mark.asyncio
async def test_hardware_after_sales_and_star_leaf_processing(tenv):
    form_id = await install_form(tenv)
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    now = datetime.now(timezone.utc)
    async with factory() as s:
        for category_id, name in ((2322, "硬件故障"), (2399, "星座系统处理")):
            if await s.get(TicketCategory, category_id) is None:
                s.add(TicketCategory(id=category_id, parent_id=None, name=name, level=1, sort_order=1,
                                     is_active=True, created_at=now, updated_at=now))
        star_group = SkillGroup(name="星座大系统负责人")
        star_user = User(username="processing-star", name="星座处理人", role="handler", password_hash="x")
        s.add_all([star_group, star_user])
        await s.flush()
        s.add(UserSkillGroup(user_id=star_user.id, skill_group_id=star_group.id, is_dispatcher=True))
        for category_id, department in ((2322, "售后"), (2399, "星座大系统负责人")):
            if (await s.execute(select(DispatchChain).where(DispatchChain.category_id == category_id))).scalar_one_or_none() is None:
                s.add(DispatchChain(category_id=category_id, steps=[{"order": 1, "department_code": department}]))
        await s.commit()
        star_id = star_user.id
    hardware, aftersales_owner = await opened(tenv, 2322)
    star = await tenv["create_ticket"](category_id=2399)
    star = await tenv["patch"](star["id"], {"state": "open", "owner_id": star_id})
    for ticket, owner in ((hardware, aftersales_owner), (star, star_id)):
        with as_user(owner, "handler"):
            detail = await tenv["get"](ticket["id"])
            assert detail["node_context"]["node_type"] == "processing"
            assert detail["current_form"]["form_definition_id"] == form_id


@pytest.mark.asyncio
async def test_triage_node_cannot_complete_processing(renv):
    form_id = await install_form(renv)
    ticket = await renv["create_ticket"]()
    assert (await renv["client"].get(f"/api/v1/tickets/{ticket['id']}")).json()["node_context"]["node_type"] == "assignment"
    body = request(ticket, form_id)
    body["expected_state"] = "pending"
    response = await renv["client"].post(f"/api/v1/tickets/{ticket['id']}/node-submit",
        data={"payload": json.dumps(body)})
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_invalid_attachment_rolls_back_processing(tenv, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    form_id = await install_form(tenv)
    ticket, owner = await opened(tenv)
    response = await submit(tenv, ticket, form_id, owner,
        files=[("attachments", ("script.html", b"<script>x</script>", "text/html"))])
    assert response.status_code == 422
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        assert (await s.get(Ticket, ticket["id"])).state == "open"
        assert not (await s.execute(select(TicketNodeSubmission).where(TicketNodeSubmission.ticket_id == ticket["id"]))).scalars().all()
        assert not (await s.execute(select(Article).where(Article.ticket_id == ticket["id"]))).scalars().all()
    assert not [path for path in tmp_path.rglob("*") if path.is_file()]
