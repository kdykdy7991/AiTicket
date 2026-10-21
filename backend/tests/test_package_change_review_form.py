"""Package change uses separate review and lightweight execution forms."""

import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import settings
from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.node_form import TicketNodeSubmission
from app.models.ticket import Article, ArticleAttachment, Ticket
from app.models.user import User
from scripts.seed_package_change_execute_form import seed_package_change_execute_form
from scripts.seed_package_change_review_form import seed_package_change_review_form
from scripts.seed_v016_opinion_forms import seed_v016_opinion_forms
from test_processing_form import install_form, request
from test_transfer import tenv
from test_workflow_regression import as_user


@pytest.mark.asyncio
async def test_package_change_review_then_execution(tenv, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))
    base_form_id = await install_form(tenv)
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    async with factory() as db:
        category = await db.get(TicketCategory, 2203)
        category.requires_callback = True
        chain = (await db.execute(select(DispatchChain).where(DispatchChain.category_id == 2203))).scalar_one()
        chain.steps = [{"order": 1, "department_code": "市场生态部"},
                       {"order": 2, "department_code": "业务支撑组"}]
        market = SkillGroup(name="市场生态部")
        support = SkillGroup(name="业务支撑组")
        reviewer = User(username="package-reviewer", name="套餐审核人", role="handler", password_hash="x")
        executor = User(username="package-executor", name="套餐执行人", role="handler", password_hash="x")
        db.add_all([market, support, reviewer, executor])
        await db.flush()
        db.add_all([UserSkillGroup(user_id=reviewer.id, skill_group_id=market.id, is_dispatcher=True),
                    UserSkillGroup(user_id=executor.id, skill_group_id=support.id, is_dispatcher=True)])
        await db.commit()
        reviewer_id, executor_id = reviewer.id, executor.id

    await seed_package_change_review_form(factory)
    await seed_package_change_execute_form(factory)
    await seed_v016_opinion_forms(factory)
    ticket = await tenv["create_ticket"](category_id=2203)
    assert ticket["category_id"] == 2203
    assert ticket["skill_group_name"] == "市场生态部"
    assert ticket["callback_required"] is True
    ticket = await tenv["patch"](ticket["id"], {"state": "open", "owner_id": reviewer_id})
    with as_user(reviewer_id, "handler"):
        detail = await tenv["get"](ticket["id"])
        assert detail["node_context"]["node_type"] == "processing"
        review_form = detail["current_form"]
        assert review_form["code"] == "package_change_review_v2"
        assert [field["field_key"] for field in review_form["fields"]] == ["new_package_name", "processing_opinion"]
        assert "can_note" not in detail
        note = await tenv["client"].post(f"/api/v1/tickets/{ticket['id']}/articles",
            data={"type": "note", "body": "重复的过程回复"})
        assert note.status_code == 422
        missing = request(ticket, review_form["form_definition_id"])
        missing["form_version"] = review_form["version"]
        missing["values"] = {"processing_opinion": "审核通过"}
        response = await tenv["client"].post(f"/api/v1/tickets/{ticket['id']}/node-submit",
            data={"payload": json.dumps(missing)})
        assert response.status_code == 422
        hold = await tenv["client"].patch(f"/api/v1/tickets/{ticket['id']}", json={
            "state": "on_hold", "reason": "等待申请单", "hold_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
        assert hold.status_code == 200, hold.text
        assert (await tenv["get"](ticket["id"]))["node_context"]["node_type"] == "processing"
        resume = await tenv["client"].patch(f"/api/v1/tickets/{ticket['id']}", json={
            "state": "open", "reason": "申请单已到"})
        assert resume.status_code == 200, resume.text
        assert (await tenv["get"](ticket["id"]))["current_form"]["code"] == "package_change_review_v2"
        payload = request(ticket, review_form["form_definition_id"])
        payload["form_version"] = review_form["version"]
        payload["values"] = {"new_package_name": "企业通信套餐", "processing_opinion": "审核通过"}
        result = await tenv["client"].post(f"/api/v1/tickets/{ticket['id']}/node-submit",
            data={"payload": json.dumps(payload)})
    assert result.status_code == 200, result.text
    transferred = result.json()["data"]
    assert transferred["state"] == "pending" and transferred["dispatch_step_index"] == 1
    assert transferred["category_id"] == 2203 and transferred["callback_required"] is True
    assert transferred["skill_group_name"] == "业务支撑组"
    assert transferred["node_context"]["node_type"] == "processing"

    async with factory() as db:
        submission = (await db.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket["id"]))).scalar_one()
        assert submission.data == {"new_package_name": "企业通信套餐"}
        assert submission.action_type == "transfer"
        attachments = (await db.execute(select(ArticleAttachment).where(
            ArticleAttachment.article_id == submission.article_id))).scalars().all()
        assert len(attachments) == 0

    next_ticket = await tenv["patch"](ticket["id"], {"state": "open", "owner_id": executor_id})
    with as_user(executor_id, "handler"):
        execution_detail = await tenv["get"](ticket["id"])
        execution_form = execution_detail["current_form"]
        assert execution_form["code"] == "package_change_execute_v3"
        assert execution_form["form_definition_id"] != base_form_id
        assert [field["field_key"] for field in execution_form["fields"]] == ["processing_opinion"]
        assert next(field for field in execution_form["fields"] if field["field_key"] == "processing_opinion")["label"] == "处理意见（结论）"
        hold = await tenv["client"].patch(f"/api/v1/tickets/{ticket['id']}", json={
            "state": "on_hold", "reason": "等待操作窗口", "hold_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
        assert hold.status_code == 200, hold.text
        assert (await tenv["get"](ticket["id"]))["node_context"]["node_type"] == "processing"
        resume = await tenv["client"].patch(f"/api/v1/tickets/{ticket['id']}", json={
            "state": "open", "reason": "开始操作"})
        assert resume.status_code == 200, resume.text
        payload = request(next_ticket, execution_form["form_definition_id"])
        payload["form_version"] = execution_form["version"]
        payload["values"] = {"processing_opinion": "已完成套餐变更操作"}
        missing = dict(payload, values={})
        invalid = await tenv["client"].post(f"/api/v1/tickets/{ticket['id']}/node-submit",
            data={"payload": json.dumps(missing)})
        assert invalid.status_code == 422
        completed = await tenv["client"].post(f"/api/v1/tickets/{ticket['id']}/node-submit",
            data={"payload": json.dumps(payload)})
    assert completed.status_code == 200, completed.text
    resolved = completed.json()["data"]
    assert resolved["state"] == "resolved" and resolved["callback_required"] is True
    assert resolved["node_context"]["node_type"] == "closure"
    async with factory() as db:
        submissions = (await db.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket["id"]).order_by(TicketNodeSubmission.id))).scalars().all()
        assert len(submissions) == 2
        assert submissions[1].data == {}
        article = await db.get(Article, submissions[1].article_id)
        assert article.body == "已完成套餐变更操作"
        attachments = (await db.execute(select(ArticleAttachment).where(
            ArticleAttachment.article_id == article.id))).scalars().all()
        assert len(attachments) == 0
        stored_ticket = await db.get(Ticket, ticket["id"])
        assert stored_ticket.root_cause is None


@pytest.mark.asyncio
async def test_package_change_form_seed_is_idempotent_and_base_unchanged(tenv):
    base_form_id = await install_form(tenv)
    factory = async_sessionmaker(tenv["engine"], class_=AsyncSession, expire_on_commit=False)
    await seed_package_change_execute_form(factory)
    await seed_package_change_execute_form(factory)
    from app.models.node_form import FormBinding, FormDefinition
    async with factory() as db:
        forms = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "package_change_execute_v1"))).scalars().all()
        assert len(forms) == 1
        bindings = (await db.execute(select(FormBinding).where(
            FormBinding.form_definition_id == forms[0].id))).scalars().all()
        assert len(bindings) == 1
        base = await db.get(FormDefinition, base_form_id)
        assert base.code == "processing_v1" and len(base.fields) == 7
