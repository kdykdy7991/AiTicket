"""Second-level constellation triage keeps category as the only routing input."""

from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import select

from app.models.category import TicketCategory
from app.models.dispatch import DispatchChain
from app.models.group import SkillGroup, UserSkillGroup
from app.models.node_form import FormBinding, FormDefinition, TicketNodeSubmission
from app.models.ticket import Article, Ticket
from app.models.user import User
from scripts.seed_constellation_triage_form import seed_constellation_triage_form, seed_constellation_route_form
from scripts.seed_constellation_response_form import seed_constellation_response_form
from scripts.seed_constellation_confirmation_form import seed_constellation_confirmation_form
from scripts.seed_constellation_analysis_form import seed_constellation_analysis_form
from scripts.seed_phone_feedback_form import seed_phone_feedback_form
from test_refine import async_sessionmaker_for, renv
from test_triage_form import install_form as install_after_sales_form, payload as triage_payload
from test_workflow_regression import as_user


TARGETS = ((2311, "核心网系统", "软件开发组"),
           (2312, "测运控系统", "测运控组"),
           (2313, "卫星系统", "整星产品"))


@pytest.mark.asyncio
async def test_constellation_lead_confirms_and_assigns_target_department_member(renv):
    factory, ticket_id, lead_id, users, _ = await setup_triage(renv)
    await seed_constellation_route_form(factory)
    await seed_constellation_triage_form(factory)
    await seed_constellation_route_form(factory)
    with as_user(lead_id, "handler"):
        form = (await renv["client"].get(
            f"/api/v1/tickets/{ticket_id}/current-form", params={"target_category_id": 2311},
        )).json()
        assert form["code"] == "constellation_triage_v2"
        assert [(field["field_key"], field["label"], field["required"]) for field in form["fields"]] == [
            ("confirmation_info", "确认信息", True),
        ]
        body = {"target_category_id": 2311, "form_definition_id": form["form_definition_id"],
                "form_version": 2, "values": {"confirmation_info": "确认由软件开发组处理"}}
        assert (await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit", json=body)).status_code == 422
        body["assigned_owner_id"] = users[2312]
        assert (await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit", json=body)).status_code == 422
        body["assigned_owner_id"] = users[2311]
        body["values"] = {}
        assert (await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit", json=body)).status_code == 422
        body["values"] = {"confirmation_info": "确认由软件开发组处理"}
        response = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit", json=body)
        assert response.status_code == 200, response.text
    result = response.json()["data"]
    assert result["category_id"] == 2311
    assert result["owner_id"] == users[2311]
    assert result["node_context"]["node_type"] == "response_plan"
    assert [step["stage"] for step in result["dispatch_chain_steps"]] == [
        "response_plan", "response_confirmation", "analysis", "phone_feedback",
    ]
    async with factory() as db:
        from app.models.ticket import TicketStateLog
        submission = (await db.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket_id,
            TicketNodeSubmission.form_definition_id == form["form_definition_id"],
        ))).scalar_one()
        assert submission.data == {"confirmation_info": "确认由软件开发组处理"}
        log = await db.get(TicketStateLog, submission.state_log_id)
        assert log.owner_id_snapshot == users[2311]
        assert "确认信息：确认由软件开发组处理" in log.reason


@pytest.mark.asyncio
@pytest.mark.parametrize("confirmation_action, reason_category, expected_stage", [
    ("confirm", "technical", "analysis"),
    ("confirm", "management", "analysis"),
    ("confirm", "technical_management", "analysis"),
    ("return", None, "response_plan"),
])
async def test_professional_submits_response_measures_to_after_sales(renv, confirmation_action, reason_category, expected_stage):
    factory, ticket_id, lead_id, users, _ = await setup_triage(renv)
    await seed_constellation_route_form(factory)
    await seed_constellation_response_form(factory)
    await seed_constellation_confirmation_form(factory)
    await seed_constellation_analysis_form(factory)
    with as_user(lead_id, "handler"):
        form = (await renv["client"].get(
            f"/api/v1/tickets/{ticket_id}/current-form", params={"target_category_id": 2311},
        )).json()
        response = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit", json={
            "target_category_id": 2311, "form_definition_id": form["form_definition_id"],
            "form_version": form["version"], "assigned_owner_id": users[2311],
            "values": {"confirmation_info": "由软件开发组处理"},
        })
        assert response.status_code == 200, response.text
    ticket = response.json()["data"]
    with as_user(users[2311], "handler"):
        detail = (await renv["client"].get(f"/api/v1/tickets/{ticket_id}")).json()
        form = detail["current_form"]
        assert form["code"] == "constellation_response_plan_v1"
        assert [(f["field_key"], f["required"]) for f in form["fields"]] == [
            ("initial_investigation", True), ("temporary_measure", True),
            ("long_term_measure", False), ("planned_completion_at", False),
        ]
        body = {
            "form_definition_id": form["form_definition_id"], "form_version": 1,
            "expected_category_id": ticket["category_id"],
            "expected_department_id": ticket["skill_group_id"],
            "expected_dispatch_step_index": 0, "expected_state": ticket["state"],
            "values": {"initial_investigation": "确认链路中断"},
        }
        failed = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/node-submit",
                                           data={"payload": json.dumps(body)})
        assert failed.status_code == 422
        body["values"]["temporary_measure"] = "重启链路"
        submitted = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/node-submit",
                                              data={"payload": json.dumps(body)})
        assert submitted.status_code == 200, submitted.text
    result = submitted.json()["data"]
    assert result["node_context"]["node_type"] == "response_confirmation"
    assert result["dispatch_step_index"] == 1
    assert result["skill_group_name"] == "售后"
    assert result["owner_id"] == result["dispatch_chain_steps"][1]["assigned_owner_id"]
    assert result["owner_id"] != users[2311]
    with as_user(users[2311], "handler"):
        forbidden = await renv["client"].get(f"/api/v1/tickets/{ticket_id}/current-form")
        assert forbidden.status_code == 403
    with as_user(result["owner_id"], "handler"):
        detail = (await renv["client"].get(f"/api/v1/tickets/{ticket_id}")).json()
        assert not any(action["action"] == "return" for action in detail["node_context"]["allowed_actions"])
        form = detail["current_form"]
        assert form["code"] == "constellation_response_confirmation_v1"
        body = {
            "form_definition_id": form["form_definition_id"], "form_version": 1,
            "expected_category_id": result["category_id"],
            "expected_department_id": result["skill_group_id"],
            "expected_dispatch_step_index": 1, "expected_state": result["state"],
            "action": confirmation_action, "values": {},
        }
        if confirmation_action == "return":
            missing_reason = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/node-submit",
                                                       data={"payload": json.dumps(body)})
            assert missing_reason.status_code == 422
            body["values"] = {"return_reason": "措施无效，请重新排查"}
        else:
            body["values"] = {"plan_confirmation_comment": ""}
        confirmed = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/node-submit",
                                               data={"payload": json.dumps(body)})
        assert confirmed.status_code == 200, confirmed.text
    next_ticket = confirmed.json()["data"]
    assert next_ticket["node_context"]["node_type"] == expected_stage
    assert next_ticket["owner_id"] == users[2311]
    assert next_ticket["dispatch_step_index"] == (2 if confirmation_action == "confirm" else 0)
    if confirmation_action == "return":
        with as_user(users[2311], "handler"):
            revision_form = (await renv["client"].get(f"/api/v1/tickets/{ticket_id}/current-form")).json()
            assert revision_form["code"] == "constellation_response_plan_v1"
            values = {field["field_key"]: field["value"] for field in revision_form["fields"]}
            assert values["initial_investigation"] == "确认链路中断"
            assert values["temporary_measure"] == "重启链路"
    else:
        with as_user(users[2311], "handler"):
            analysis_form = (await renv["client"].get(f"/api/v1/tickets/{ticket_id}/current-form")).json()
            assert analysis_form["code"] == "constellation_analysis_v1"
            common = {
                "reason_category": reason_category,
                "rectification_completion_at": "2026-12-31T18:00:00+08:00",
                "process_analysis": "分析了故障全过程",
                "long_term_rectification_measure": "固化整改措施",
                "verification_situation": "复测通过",
            }
            technical = {"mechanism_analysis": "机理已核实", "analysis_report": "横向排查完成", "conclusion": "验证闭环"}
            management = {"responsible_person": "责任人甲", "rule_improvement": "制度已修订"}
            analysis_body = {
                "form_definition_id": analysis_form["form_definition_id"], "form_version": 1,
                "expected_category_id": next_ticket["category_id"],
                "expected_department_id": next_ticket["skill_group_id"],
                "expected_dispatch_step_index": 2, "expected_state": next_ticket["state"],
                "values": common,
            }
            missing_branch = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/node-submit",
                                                       data={"payload": json.dumps(analysis_body)})
            assert missing_branch.status_code == 422
            if reason_category in ("technical", "technical_management"):
                analysis_body["values"].update(technical)
            if reason_category in ("management", "technical_management"):
                analysis_body["values"].update(management)
            analyzed = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/node-submit",
                                                 data={"payload": json.dumps(analysis_body)})
            assert analyzed.status_code == 200, analyzed.text
        after_analysis = analyzed.json()["data"]
        assert after_analysis["node_context"]["node_type"] == "phone_feedback"
        assert after_analysis["dispatch_step_index"] == 3
        assert after_analysis["owner_id"] == result["owner_id"]
        assert after_analysis["skill_group_name"] == "售后"
        await seed_phone_feedback_form(factory)
        with as_user(result["owner_id"], "handler"):
            feedback_form = (await renv["client"].get(f"/api/v1/tickets/{ticket_id}/current-form")).json()
            assert feedback_form["code"] == "phone_feedback_v2"
            feedback = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/node-submit", data={
                "payload": json.dumps({
                    "form_definition_id": feedback_form["form_definition_id"],
                    "form_version": feedback_form["version"],
                    "expected_category_id": after_analysis["category_id"],
                    "expected_department_id": after_analysis["skill_group_id"],
                    "expected_dispatch_step_index": 3,
                    "expected_state": after_analysis["state"],
                    "values": {"phone_feedback_result": "已向客户说明处理结果"},
                }),
            })
            assert feedback.status_code == 200, feedback.text
        assert feedback.json()["data"]["state"] == "resolved"
    async with factory() as db:
        submission = (await db.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket_id,
            TicketNodeSubmission.node_type == "response_plan",
        ))).scalar_one()
        assert submission.data == {
            "initial_investigation": "确认链路中断", "temporary_measure": "重启链路",
        }
        confirmation = (await db.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket_id,
            TicketNodeSubmission.node_type == "response_confirmation",
        ))).scalar_one()
        assert confirmation.action_type == ("confirm_plan" if confirmation_action == "confirm" else "return_plan")


async def setup_triage(env):
    after_sales_id = await install_after_sales_form(env)
    factory = async_sessionmaker_for(env["engine"])
    async with factory() as db:
        (await db.get(TicketCategory, 2301)).requires_callback = True
        lead = (await db.execute(select(User).where(User.username == "triage-star-owner"))).scalar_one()
        users = {}
        for category_id, category_name, department in TARGETS:
            category = await db.get(TicketCategory, category_id)
            if category is None:
                category = TicketCategory(id=category_id, parent_id=2310, name=category_name,
                                          level=3, sort_order=category_id - 2310, is_active=True,
                                          created_at=datetime.now(timezone.utc), updated_at=datetime.now(timezone.utc))
                db.add(category)
            group = SkillGroup(name=department)
            user = User(username=f"constellation-{category_id}", name=f"{department}处理人",
                        role="handler", password_hash="x")
            db.add_all([group, user])
            await db.flush()
            db.add(UserSkillGroup(user_id=user.id, skill_group_id=group.id, is_dispatcher=True))
            db.add(DispatchChain(category_id=category_id, steps=[
                {"order": 1, "department_code": department},
                {"order": 2, "department_code": "售后", "stage": "phone_feedback"},
            ]))
            users[category_id] = user.id
        await db.commit()
        lead_id = lead.id
    await seed_constellation_triage_form(factory)
    ticket = await env["create_ticket"]()
    from test_refine import assign_after_sales
    await assign_after_sales(env, ticket["id"])
    first = await env["client"].post(f"/api/v1/tickets/{ticket['id']}/triage-submit",
                                     json=triage_payload(after_sales_id, 2310, initial_opinion="售后初查"))
    assert first.status_code == 200, first.text
    star = first.json()["data"]
    assert star["category_id"] == 2310
    assert star["node_context"]["node_type"] == "triage"
    assert star["skill_group_name"] == "星座大系统负责人"
    assert star["callback_required"] is True
    return factory, ticket["id"], lead_id, users, after_sales_id


@pytest.mark.asyncio
@pytest.mark.parametrize("target_id,category_name,department", TARGETS)
async def test_constellation_triage_routes_each_direct_child(renv, target_id, category_name, department):
    factory, ticket_id, lead_id, users, after_sales_id = await setup_triage(renv)
    with as_user(lead_id, "handler"):
        detail = (await renv["client"].get(f"/api/v1/tickets/{ticket_id}")).json()
        form = detail["current_form"]
        assert form["code"] == "constellation_triage_v1" and form["version"] == 1
        assert [(field["field_key"], field["required"]) for field in form["fields"]] == [("initial_opinion", True)]
        options = detail["refine_options"]
        assert {option["id"] for option in options} == {2311, 2312, 2313}
        assert {option["id"]: option["next_department"] for option in options} == {
            2311: "软件开发组", 2312: "测运控组", 2313: "整星产品"}
        body = triage_payload(form["form_definition_id"], target_id, initial_opinion="负责人初查")
        missing = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json={**body, "values": {}})
        assert missing.status_code == 422
        no_target = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json={"form_definition_id": form["form_definition_id"], "form_version": 1,
                  "values": {"initial_opinion": "负责人初查"}})
        assert no_target.status_code == 422
        invalid_child = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json=triage_payload(form["form_definition_id"], 2302, initial_opinion="负责人初查"))
        assert invalid_child.status_code == 400
        forged = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json={**body, "target_department": "伪造部门"})
        assert forged.status_code == 422
        submitted = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json=body)
        assert submitted.status_code == 200, submitted.text
    result = submitted.json()["data"]
    assert result["category_id"] == target_id
    assert result["dispatch_chain_steps"] == [
        {"order": 1, "department_code": department},
        {"order": 2, "department_code": "售后", "stage": "phone_feedback"},
    ]
    assert result["dispatch_step_index"] == 0
    assert result["skill_group_name"] == department
    assert result["node_context"]["node_type"] == "processing"
    assert result["callback_required"] is True
    async with factory() as db:
        submissions = (await db.execute(select(TicketNodeSubmission).where(
            TicketNodeSubmission.ticket_id == ticket_id).order_by(TicketNodeSubmission.id))).scalars().all()
        assert len(submissions) == 2
        assert submissions[0].form_definition_id == after_sales_id
        assert submissions[1].data == {"initial_opinion": "负责人初查"}
        assert submissions[1].article_id is None
        assert not (await db.execute(select(Article).where(Article.ticket_id == ticket_id))).scalars().all()
    await renv["patch"](ticket_id, {"state": "open", "owner_id": users[target_id]})
    with as_user(users[target_id], "handler"):
        held = await renv["client"].patch(f"/api/v1/tickets/{ticket_id}", json={
            "state": "on_hold", "reason": "等待处理窗口",
            "hold_until": (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()})
        assert held.status_code == 200, held.text
        resumed = await renv["client"].patch(f"/api/v1/tickets/{ticket_id}", json={
            "state": "open", "reason": "继续处理"})
        assert resumed.status_code == 200, resumed.text


@pytest.mark.asyncio
async def test_constellation_requires_target_chain_and_seed_is_idempotent(renv):
    factory, ticket_id, lead_id, _, _ = await setup_triage(renv)
    await seed_constellation_triage_form(factory)
    async with factory() as db:
        forms = (await db.execute(select(FormDefinition).where(
            FormDefinition.code == "constellation_triage_v1"))).scalars().all()
        assert len(forms) == 1
        bindings = (await db.execute(select(FormBinding).where(
            FormBinding.form_definition_id == forms[0].id))).scalars().all()
        assert len(bindings) == 1
        chain = (await db.execute(select(DispatchChain).where(DispatchChain.category_id == 2311))).scalar_one()
        chain.enabled = False
        await db.commit()
        form_id = forms[0].id
    with as_user(lead_id, "handler"):
        failed = await renv["client"].post(f"/api/v1/tickets/{ticket_id}/triage-submit",
            json=triage_payload(form_id, 2311, initial_opinion="负责人初查"))
        assert failed.status_code == 422
    async with factory() as db:
        assert (await db.get(Ticket, ticket_id)).category_id == 2310
