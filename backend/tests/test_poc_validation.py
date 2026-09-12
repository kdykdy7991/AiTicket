"""必填校验、非法跳转、旧枚举、并发冲突与三条退回路径测试。"""

from app.domain.poc_workflow import TicketAction
from helpers import run_steps

# ── 建单校验 ───────────────────────────────────────────────


async def test_create_missing_required_field_returns_400(api):
    api.as_("presales01")
    resp = await api.create_ticket(title=None)
    assert resp.status_code == 400, resp.text
    assert "title" in resp.text


async def test_create_rejects_legacy_fields(api):
    api.as_("presales01")
    resp = await api.create_ticket(customer_phone="13800000000")
    assert resp.status_code == 422, resp.text

    resp = await api.create_ticket(dispatcher_id=1)
    assert resp.status_code == 422, resp.text


async def test_create_rejects_legacy_priority(api):
    api.as_("presales01")
    for legacy in ("p1_urgent", "p2_high", "p3_normal", "p4_enterprise"):
        resp = await api.create_ticket(priority=legacy)
        assert resp.status_code == 422, f"{legacy} 不应被接受：{resp.text}"


async def test_create_requires_valid_approver(api):
    api.as_("presales01")
    resp = await api.create_ticket(approver_id=api.uid("quality01"))
    assert resp.status_code == 400, resp.text
    assert "approver" in resp.text

    resp = await api.create_ticket(approver_id=999999)
    assert resp.status_code == 404, resp.text


async def test_create_rejected_for_non_presales_role(api):
    api.as_("taskforce01")
    resp = await api.create_ticket()
    assert resp.status_code == 403, resp.text


# ── 旧枚举不进新接口 ───────────────────────────────────────


async def test_legacy_role_filter_returns_422(api):
    api.as_("admin")
    for legacy in ("agent", "handler", "dispatcher"):
        resp = await api.c.get("/api/v1/users", params={"role": legacy})
        assert resp.status_code == 422, f"{legacy} 不应被接受"


async def test_legacy_state_and_priority_filters_return_422(api):
    api.as_("quality01")
    for legacy in ("pending", "open", "resolved", "on_hold", "archived"):
        resp = await api.c.get("/api/v1/tickets", params={"state": legacy})
        assert resp.status_code == 422, f"{legacy} 不应被接受"

    resp = await api.c.get("/api/v1/tickets", params={"priority": "p1_urgent"})
    assert resp.status_code == 422


async def test_legacy_actions_are_rejected(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    api.as_("approver01")
    version = (await api.detail(ticket_id))["state_version"]
    for legacy in ("open", "resolve", "dispatch", "archive", "callback"):
        resp = await api.c.post(
            f"/api/v1/tickets/{ticket_id}/actions",
            json={"action": legacy, "expected_version": version},
        )
        assert resp.status_code == 422, f"{legacy} 不应被接受"


# ── 动作校验 ───────────────────────────────────────────────


async def test_action_requires_expected_version(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    api.as_("approver01")
    resp = await api.c.post(
        f"/api/v1/tickets/{ticket_id}/actions", json={"action": "approve"}
    )
    assert resp.status_code == 422, resp.text


async def test_version_conflict_returns_409(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    api.as_("approver01")
    version = (await api.detail(ticket_id))["state_version"]

    await api.action(ticket_id, "approve", version=version)
    resp = await api.action(ticket_id, "approve", version=version, expect=409)
    assert "已被他人更新" in resp.text

    # 刷新后可以继续正常操作
    refreshed = await api.detail(ticket_id)
    assert refreshed["state_version"] == version + 1


async def test_missing_required_action_payload_returns_400(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 1)  # pending_routing

    api.as_("taskforce01")
    resp = await api.action(ticket_id, "route", payload={}, expect=400)
    assert "skill_group_id" in resp.text and "subsystem_owner_id" in resp.text

    resp = await api.action(
        ticket_id, "route", payload={"skill_group_id": api.sg("系统总体")}, expect=400
    )
    assert "subsystem_owner_id" in resp.text


async def test_route_rejects_wrong_subsystem_owner(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 1)

    api.as_("taskforce01")
    # 角色不符
    resp = await api.action(
        ticket_id,
        "route",
        payload={
            "skill_group_id": api.sg("系统总体"),
            "subsystem_owner_id": api.uid("quality01"),
        },
        expect=400,
    )
    assert "subsystem" in resp.text

    # 用户不属于该分系统
    resp = await api.action(
        ticket_id,
        "route",
        payload={
            "skill_group_id": api.sg("系统总体"),
            "subsystem_owner_id": api.uid("subsystem02"),
        },
        expect=400,
    )
    assert "不属于所选分系统" in resp.text

    # 分系统不存在
    resp = await api.action(
        ticket_id,
        "route",
        payload={"skill_group_id": 999999, "subsystem_owner_id": api.uid("subsystem01")},
        expect=404,
    )


async def test_unknown_payload_field_returns_422(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    api.as_("approver01")
    resp = await api.action(
        ticket_id, "approve", payload={"owner_id": 1}, expect=422
    )
    assert "不支持的字段" in resp.text


async def test_invalid_verification_status_returns_422(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 5)  # pending_quality_review

    api.as_("quality01")
    resp = await api.action(
        ticket_id,
        "pass_review",
        payload={
            "verification_status": "done",
            "verification_conclusion": "通过",
            "quality_review_result": "同意",
        },
        expect=422,
    )
    assert "verification_status" in resp.text


async def test_register_defect_requires_defect_info(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 6)  # pending_defect_registration

    api.as_("quality01")
    resp = await api.action(
        ticket_id, "register_defect", payload={"defect_id": "BUG-1"}, expect=400
    )
    assert "defect_repository_path" in resp.text

    resp = await api.action(
        ticket_id,
        "register_defect",
        payload={"defect_id": "BUG-1", "defect_repository_path": "   "},
        expect=400,
    )
    assert "defect_repository_path" in resp.text

    # 补全后可以闭环
    detail = await api.acted(
        ticket_id,
        "register_defect",
        payload={"defect_id": "BUG-1", "defect_repository_path": "svn://svn/poc#1"},
    )
    assert detail["state"] == "closed"


async def test_terminal_ticket_rejects_further_actions(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 7)  # closed

    api.as_("quality01")
    version = (await api.detail(ticket_id))["state_version"]
    for action in ("register_defect", "pass_review", "cancel"):
        resp = await api.action(ticket_id, action, version=version, expect=400)
        assert "终态" in resp.text


async def test_cancel_requires_reason_and_is_terminal(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await api.action(ticket_id, "cancel", expect=400)  # 缺原因

    detail = await api.acted(ticket_id, "cancel", comment="客户已取消 POC")
    assert detail["state"] == "cancelled"
    assert detail["allowed_actions"] == []
    assert detail["closed_at"] is not None


# ── 退回路径 ───────────────────────────────────────────────


async def test_reject_then_resubmit_returns_to_pending_approval(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    creator_id = api.uid("presales01")

    api.as_("approver01")
    await api.action(ticket_id, "reject", expect=400)  # 缺原因
    detail = await api.acted(ticket_id, "reject", comment="问题描述不足，请补充")
    assert detail["state"] == "returned"
    assert detail["return_to_state"] == "pending_approval"
    assert detail["current_responsible_role"] == "presales"
    assert detail["current_responsible_user_id"] == creator_id

    api.as_("presales01")
    assert "resubmit" in (await api.detail(ticket_id))["allowed_actions"]
    patched = await api.c.patch(
        f"/api/v1/tickets/{ticket_id}", json={"description": "补充后的现象描述"}
    )
    assert patched.status_code == 200, patched.text

    detail = await api.acted(ticket_id, "resubmit")
    assert detail["state"] == "pending_approval"
    assert detail["return_to_state"] is None

    api.as_("approver01")
    detail = await api.acted(ticket_id, "approve", comment="补充完整，同意")
    assert detail["state"] == "pending_routing"


async def test_return_path_taskforce_node_to_pending_approval(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 1)  # pending_routing

    api.as_("taskforce01")
    await api.action(ticket_id, "return", payload={}, expect=400)  # 缺原因
    detail = await api.acted(ticket_id, "return", comment="问题描述不准确")

    assert detail["state"] == "returned"
    assert detail["return_to_state"] == "pending_approval"
    assert detail["current_responsible_role"] == "presales"
    assert detail["current_responsible_user_id"] == api.uid("presales01")

    # 退回节点不接受非法目标
    api.as_("presales01")
    resp = await api.action(
        ticket_id, "return", payload={"return_to_state": "processing"}, expect=400
    )
    assert "不支持动作" in resp.text or "退回" in resp.text

    detail = await api.acted(ticket_id, "resubmit", comment="已按意见修订")
    assert detail["state"] == "pending_approval"
    logs = detail["state_logs"]
    assert logs[-2]["action"] == "return"
    assert logs[-2]["comment"] == "问题描述不准确"


async def test_return_path_plan_confirmation_to_planning(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 3)  # pending_plan_confirmation

    api.as_("presales01")
    detail = await api.acted(
        ticket_id,
        "return",
        payload={"return_to_state": "planning"},
        comment="计划完成时间不可接受",
    )
    assert detail["state"] == "returned"
    assert detail["return_to_state"] == "planning"
    assert detail["current_responsible_role"] == "subsystem"
    assert detail["current_responsible_user_id"] == api.uid("subsystem01")

    api.as_("subsystem01")
    detail = await api.acted(ticket_id, "resubmit")
    assert detail["state"] == "planning"

    detail = await api.acted(
        ticket_id,
        "submit_plan",
        payload={
            "long_term_measure": "修订后的长期整改措施",
            "planned_completion_at": "2026-11-30T18:00:00+08:00",
        },
    )
    assert detail["state"] == "pending_plan_confirmation"
    assert detail["long_term_measure"] == "修订后的长期整改措施"


async def test_return_path_quality_review_to_processing(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 5)  # pending_quality_review

    api.as_("quality01")
    detail = await api.acted(ticket_id, "return", comment="分析报告缺少复现证据")
    assert detail["state"] == "returned"
    assert detail["return_to_state"] == "processing"
    assert detail["current_responsible_role"] == "subsystem"
    assert detail["current_responsible_user_id"] == api.uid("subsystem01")

    api.as_("subsystem01")
    detail = await api.acted(ticket_id, "resubmit")
    assert detail["state"] == "processing"

    detail = await api.acted(
        ticket_id,
        "submit_analysis",
        payload={
            "initial_investigation": "补充初步排查",
            "root_cause": "补充根因",
            "analysis_report": "补充复现记录与日志证据",
        },
    )
    assert detail["state"] == "pending_quality_review"

    api.as_("quality01")
    detail = await api.acted(
        ticket_id,
        "pass_review",
        payload={
            "verification_status": "temporarily_resolved",
            "verification_conclusion": "临时解决，后续跟踪",
            "quality_review_result": "同意入库",
        },
    )
    assert detail["state"] == "pending_defect_registration"
    assert detail["verification_status"] == "temporarily_resolved"


async def test_return_target_is_fixed_per_node(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 1)  # pending_routing

    api.as_("taskforce01")
    resp = await api.action(
        ticket_id,
        "return",
        payload={"return_to_state": "processing"},
        comment="目标不允许",
        expect=400,
    )
    assert "不允许退回" in resp.text


async def test_patch_field_scope_by_node(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 2)  # planning

    # 当前节点责任人不懂的字段不允许改
    api.as_("subsystem01")
    resp = await api.c.patch(f"/api/v1/tickets/{ticket_id}", json={"title": "改标题"})
    assert resp.status_code == 400, resp.text
    assert "title" in resp.text

    ok = await api.c.patch(
        f"/api/v1/tickets/{ticket_id}", json={"long_term_measure": "先写草稿措施"}
    )
    assert ok.status_code == 200, ok.text
    assert ok.json()["long_term_measure"] == "先写草稿措施"

    # 角色级节点（专项小组）没有可编辑字段
    await run_steps(api, ticket_id, 5, start=2)  # pending_quality_review
    api.as_("taskforce01")
    resp = await api.c.patch(f"/api/v1/tickets/{ticket_id}", json={"title": "改标题"})
    assert resp.status_code == 403, resp.text


# ── 不存在的问题必须 404 而不是 500 ────────────────────────


async def test_missing_ticket_returns_404_not_500(api):
    """回归：_load_detail 曾用 scalar_one()，删库后访问详情会 500。"""
    api.as_("quality01")
    missing = 999999

    resp = await api.c.get(f"/api/v1/tickets/{missing}")
    assert resp.status_code == 404, resp.text
    assert resp.json()["error"]["code"] == "问题_NOT_FOUND"

    resp = await api.c.get(f"/api/v1/tickets/{missing}/state-logs")
    assert resp.status_code == 404, resp.text

    resp = await api.c.patch(f"/api/v1/tickets/{missing}", json={"title": "x"})
    assert resp.status_code == 404, resp.text

    resp = await api.c.post(
        f"/api/v1/tickets/{missing}/actions",
        json={"action": "approve", "expected_version": 1},
    )
    assert resp.status_code == 404, resp.text

    resp = await api.c.post(
        f"/api/v1/tickets/{missing}/attachments",
        files={"files": ("证据.png", b"\x89PNG\r\n\x1a\n", "image/png")},
    )
    assert resp.status_code == 404, resp.text


async def test_deleted_ticket_detail_returns_404(api):
    """建单后删除（如清库），详情与草稿接口都应 404 而不是 500。"""
    from sqlalchemy import delete  # noqa: PLC0415

    from app.models.ticket import Ticket  # noqa: PLC0415

    api.as_("presales01")
    draft_id = (await api.create_ticket(draft=True)).json()["data"]["id"]
    assert (await api.c.get(f"/api/v1/tickets/{draft_id}")).status_code == 200

    async with api.session() as s:
        await s.execute(delete(Ticket).where(Ticket.id == draft_id))
        await s.commit()

    assert (await api.c.get(f"/api/v1/tickets/{draft_id}")).status_code == 404
    assert (
        await api.c.post(f"/api/v1/tickets/drafts/{draft_id}/submit")
    ).status_code == 404


# ── 提出人 / 提出部门必填（售前组公用账号）────────────────────


async def test_create_requires_proposer_fields(api):
    api.as_("presales01")

    resp = await api.create_ticket(proposer=None)
    assert resp.status_code == 400, resp.text
    assert "proposer" in resp.text

    resp = await api.create_ticket(proposer_department=None)
    assert resp.status_code == 400, resp.text
    assert "proposer_department" in resp.text

    resp = await api.create_ticket(proposer="   ", proposer_department="  ")
    assert resp.status_code == 400, resp.text
    assert "proposer" in resp.text and "proposer_department" in resp.text


async def test_draft_can_omit_proposer_but_submit_requires_it(api):
    api.as_("presales01")
    draft = await api.create_ticket(
        draft=True, proposer=None, proposer_department=None
    )
    assert draft.status_code == 201, draft.text
    draft_id = draft.json()["data"]["id"]
    assert draft.json()["data"]["proposer"] is None

    # 草稿直接提交 → 缺少提出人/提出部门
    resp = await api.c.post(f"/api/v1/tickets/drafts/{draft_id}/submit")
    assert resp.status_code == 400, resp.text
    assert "proposer" in resp.text

    # 提交时补齐即可
    resp = await api.c.post(
        f"/api/v1/tickets/drafts/{draft_id}/submit",
        json={"proposer": "李四", "proposer_department": "售前与解决方案部"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["state"] == "pending_approval"
    assert data["proposer"] == "李四"
    assert data["proposer_department"] == "售前与解决方案部"


async def test_proposer_fields_visible_in_list_detail_and_export(api):
    api.as_("presales01")
    ticket_id = (
        await api.create_ticket(proposer="王五", proposer_department="售前一组")
    ).json()["data"]["id"]

    api.as_("quality01")
    detail = await api.detail(ticket_id)
    assert detail["proposer"] == "王五"
    assert detail["proposer_department"] == "售前一组"

    listed = (await api.c.get("/api/v1/tickets")).json()["data"]
    row = next(t for t in listed if t["id"] == ticket_id)
    assert row["proposer"] == "王五"
    assert row["proposer_department"] == "售前一组"

    # 关键词可以按提出人/提出部门检索
    hits = (await api.c.get("/api/v1/tickets", params={"keyword": "王五"})).json()["data"]
    assert [t["id"] for t in hits] == [ticket_id]
    hits = (
        await api.c.get("/api/v1/tickets", params={"keyword": "售前一组"})
    ).json()["data"]
    assert [t["id"] for t in hits] == [ticket_id]

    export = await api.c.get("/api/v1/tickets/export")
    assert "王五" in export.text and "售前一组" in export.text


async def test_creator_can_fix_proposer_before_approval(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]

    resp = await api.c.patch(
        f"/api/v1/tickets/{ticket_id}",
        json={"proposer": "赵六", "proposer_department": "售前二组"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["proposer"] == "赵六"
    assert resp.json()["proposer_department"] == "售前二组"

    # 审批阶段之后（非创建人可编辑节点）不允许再改
    api.as_("approver01")
    await api.action(ticket_id, "approve")
    api.as_("quality01")
    resp = await api.c.patch(f"/api/v1/tickets/{ticket_id}", json={"proposer": "越权"})
    assert resp.status_code == 403, resp.text


async def test_merged_away_actions_are_rejected(api):
    """流程合并后 confirm_problem / accept 不再是合法动作。"""
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 1)  # pending_routing：专项小组节点

    api.as_("taskforce01")
    await api.action(ticket_id, "confirm_problem", expect=422)
    await api.action(ticket_id, "accept", expect=422)

    # 合并后的正向动作一次完成确认与流转
    detail = await api.acted(
        ticket_id,
        "route",
        comment="问题描述准确，转终端系统",
        payload={
            "skill_group_id": api.sg("终端系统"),
            "subsystem_owner_id": api.uid("subsystem03"),
        },
    )
    assert detail["state"] == "planning"
    assert detail["confirmation_comment"] == "问题描述准确，转终端系统"
    assert detail["skill_group_name"] == "终端系统"
    assert detail["subsystem_owner_name"] == "余华伟"
    assert detail["current_responsible_role"] == "subsystem"
    assert detail["current_responsible_user_id"] == api.uid("subsystem03")
