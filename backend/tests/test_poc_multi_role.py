"""一人多角色（user_roles）契约测试。

契约：docs/poc/00_poc_workflow_development_contract.md 第 2 节、6.4 节。
"""

import pytest
from sqlalchemy import select

from app.models.user import User, UserRole


async def _login(api, username: str, password: str) -> dict:
    resp = await api.c.post(
        "/api/v1/auth/login", json={"username": username, "password": password}
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_login_returns_roles_list(api):
    api.as_("presales01")
    body = await _login(api, "presales01", "skdy123")
    assert body["user"]["roles"] == ["presales"]

    # 多角色用户按契约固定顺序返回
    api.as_("multi01")
    body = await _login(api, "multi01", "skdy123")
    assert body["user"]["roles"] == ["approver", "subsystem"]


async def test_one_account_covers_two_roles_in_same_ticket(api):
    """同一个账号先当批准人、后当分系统负责人，走完两个节点的动作。"""
    api.as_("presales01")
    created = await api.create_ticket(approver_id=api.uid("multi01"))
    assert created.status_code == 201, created.text
    ticket_id = created.json()["data"]["id"]

    # 阶段一：作为批准人
    api.as_("multi01")
    pending = await api.detail(ticket_id)
    assert pending["allowed_actions"] == ["approve", "reject"]

    approved = await api.acted(ticket_id, "approve", comment="同意")
    assert approved["state"] == "pending_routing"

    # 专项小组一步确认并流转给同一个账号（它同时拥有 subsystem 角色）
    api.as_("taskforce01")
    await api.action(
        ticket_id,
        "route",
        comment="描述准确",
        payload={
            "skill_group_id": api.sg("系统总体"),
            "subsystem_owner_id": api.uid("multi01"),
        },
    )

    # 阶段二：作为分系统负责人，直接进入闭环计划制定
    api.as_("multi01")
    planning = await api.detail(ticket_id)
    assert planning["state"] == "planning"
    assert planning["allowed_actions"] == ["submit_plan"]

    planned = await api.acted(
        ticket_id,
        "submit_plan",
        payload={
            "initial_investigation": "初步排查结论",
            "long_term_measure": "修复固件",
            "planned_completion_at": "2026-12-31T18:00:00+08:00",
        },
    )
    assert planned["state"] == "pending_plan_confirmation"

    api.as_("presales01")
    await api.action(ticket_id, "confirm_plan", comment="计划认可")

    api.as_("multi01")
    analyzed = await api.acted(
        ticket_id,
        "submit_analysis",
        payload={
            "root_cause": "根因",
            "analysis_report": "报告",
        },
    )
    assert analyzed["state"] == "pending_quality_review"

    # 时间线里这条记录的操作人拥有两个角色
    api.as_("quality01")
    detail = await api.detail(ticket_id)
    assert detail["state_logs"][1]["operator_roles"] == ["approver", "subsystem"]
    assert detail["state_logs"][1]["action"] == "approve"
    assert detail["state_logs"][3]["action"] == "submit_plan"
    assert detail["state_logs"][3]["operator_roles"] == ["approver", "subsystem"]


async def test_multi_role_data_scope_is_union(api):
    """数据范围取各角色并集：本人审批的 + 本人所属分系统的。"""
    # 三条都先由售前创建（只有 presales/admin 能建单）
    api.as_("presales01")
    mine_as_approver = (
        await api.create_ticket(approver_id=api.uid("multi01"), title="多角色-待我审批")
    ).json()["data"]["id"]
    other = (
        await api.create_ticket(approver_id=api.uid("approver01"), title="多角色-别人审批")
    ).json()["data"]["id"]
    third = (
        await api.create_ticket(approver_id=api.uid("approver01"), title="多角色-别的分系统")
    ).json()["data"]["id"]

    # 把 other 流转到系统总体（multi01 所属分系统），责任人不是他
    api.as_("approver01")
    await api.action(other, "approve")
    api.as_("taskforce01")
    await api.action(
        other,
        "route",
        comment="确认信息",
        payload={
            "skill_group_id": api.sg("系统总体"),
            "subsystem_owner_id": api.uid("subsystem01"),
        },
    )

    # 第三条流转到卫星平台，multi01 不应看到
    api.as_("approver01")
    await api.action(third, "approve")
    api.as_("taskforce01")
    await api.action(
        third,
        "route",
        comment="确认信息",
        payload={
            "skill_group_id": api.sg("卫星平台"),
            "subsystem_owner_id": api.uid("subsystem02"),
        },
    )

    api.as_("multi01")
    listed = (await api.c.get("/api/v1/tickets", params={"page_size": 100})).json()["data"]
    ids = {t["id"] for t in listed}
    assert mine_as_approver in ids  # approver 范围
    assert other in ids  # subsystem 范围（同分系统）
    assert third not in ids  # 既不是他审批，也不在他分系统

    # 详情/附件同样按并集放行
    assert (await api.c.get(f"/api/v1/tickets/{other}")).status_code == 200
    assert (await api.c.get(f"/api/v1/tickets/{third}")).status_code == 403


async def test_multi_role_does_not_grant_creator_actions(api):
    """拥有 approver+subsystem 不等于拥有 presales：创建人专属动作仍被拒绝。"""
    api.as_("presales01")
    ticket_id = (await api.create_ticket(approver_id=api.uid("multi01"))).json()["data"]["id"]

    api.as_("multi01")
    detail = await api.detail(ticket_id)
    assert "cancel" not in detail["allowed_actions"]  # cancel 仅创建人/管理员
    await api.action(ticket_id, "cancel", comment="越权撤销", expect=403)


async def test_create_user_with_multiple_roles(api):
    api.as_("admin")
    resp = await api.c.post(
        "/api/v1/users",
        json={
            "username": "dual01",
            "name": "多角色-新建",
            "password": "skdy123",
            "roles": ["presales", "quality"],
            "skill_groups": [],
        },
    )
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"]["roles"] == ["presales", "quality"]

    api.as_("quality01")
    users = (await api.c.get("/api/v1/users")).json()["data"]
    dual = next(u for u in users if u["username"] == "dual01")
    assert dual["roles"] == ["presales", "quality"]

    # 两个角色的筛选都能命中同一个账号
    for role in ("presales", "quality"):
        found = (
            await api.c.get("/api/v1/users", params={"role": role})
        ).json()["data"]
        assert "dual01" in {u["username"] for u in found}

    body = await _login(api, "dual01", "skdy123")
    assert body["user"]["roles"] == ["presales", "quality"]


async def test_create_user_requires_at_least_one_role(api):
    api.as_("admin")
    resp = await api.c.post(
        "/api/v1/users",
        json={"username": "norole", "name": "无角色", "password": "skdy123", "roles": []},
    )
    assert resp.status_code == 422, resp.text

    resp = await api.c.post(
        "/api/v1/users",
        json={"username": "badrole", "name": "非法角色", "password": "skdy123", "roles": ["agent"]},
    )
    assert resp.status_code == 422, resp.text


async def test_update_user_replaces_roles_and_clears_skill_groups(api):
    api.as_("admin")
    created = await api.c.post(
        "/api/v1/users",
        json={
            "username": "dual02",
            "name": "多角色-改",
            "password": "skdy123",
            "roles": ["subsystem"],
            "skill_groups": [{"skill_group_id": api.sg("卫星平台")}],
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["data"]["id"]

    async with api.session() as s:
        links = (
            await s.execute(select(UserRole).where(UserRole.user_id == user_id))
        ).scalars().all()
        assert {link.role for link in links} == {"subsystem"}

    # 追加一个角色
    updated = await api.c.patch(
        f"/api/v1/users/{user_id}", json={"roles": ["subsystem", "taskforce"]}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["roles"] == ["taskforce", "subsystem"]

    # 去掉 subsystem 角色后分系统关联同步清空
    updated = await api.c.patch(
        f"/api/v1/users/{user_id}", json={"roles": ["taskforce"], "skill_groups": []}
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["data"]["roles"] == ["taskforce"]

    api.as_("taskforce01")
    users = (await api.c.get("/api/v1/users")).json()["data"]
    target = next(u for u in users if u["username"] == "dual02")
    assert target["skill_groups"] == []


async def test_cannot_remove_last_admin_role(api):
    api.as_("admin")
    admin_id = api.uid("admin")

    resp = await api.c.patch(f"/api/v1/users/{admin_id}", json={"roles": ["presales"]})
    assert resp.status_code == 400, resp.text
    assert "最后一个管理员" in resp.text

    resp = await api.c.delete(f"/api/v1/users/{admin_id}")
    assert resp.status_code == 400, resp.text
    assert "最后一个管理员" in resp.text

    # 仍可追加角色（不影响 admin 保留）
    ok = await api.c.patch(f"/api/v1/users/{admin_id}", json={"roles": ["admin", "quality"]})
    assert ok.status_code == 200, ok.text
    # 角色按契约固定顺序返回：presales/approver/taskforce/subsystem/quality/admin
    assert ok.json()["data"]["roles"] == ["quality", "admin"]
    await api.c.patch(f"/api/v1/users/{admin_id}", json={"roles": ["admin"]})


async def test_skill_groups_only_kept_for_subsystem_role(api):
    """roles 不含 subsystem 时，传入的 skill_groups 被忽略。"""
    api.as_("admin")
    created = await api.c.post(
        "/api/v1/users",
        json={
            "username": "dual03",
            "name": "多角色-无分系统",
            "password": "skdy123",
            "roles": ["quality"],
            "skill_groups": [{"skill_group_id": api.sg("卫星平台")}],
        },
    )
    assert created.status_code == 201, created.text
    user_id = created.json()["data"]["id"]

    api.as_("quality01")
    users = (await api.c.get("/api/v1/users")).json()["data"]
    target = next(u for u in users if u["username"] == "dual03")
    assert target["skill_groups"] == []
    assert target["roles"] == ["quality"]


@pytest.mark.parametrize("username", ["presales01", "subsystem01", "quality01"])
async def test_single_role_users_unchanged(api, username):
    """存量单角色账号行为不变。"""
    api.as_(username)
    me = (
        await api.c.get("/api/v1/users", params={"keyword": username})
    ).json()["data"]
    assert len(me) == 1
    assert len(me[0]["roles"]) == 1


async def test_user_roles_table_is_source_of_truth(api):
    """users 表不再有 role 列，角色只存在 user_roles。"""
    async with api.session() as s:
        columns = await s.run_sync(
            lambda sync_session: [
                c["name"] for c in __import__("sqlalchemy").inspect(
                    sync_session.get_bind()
                ).get_columns("users")
            ]
        )
    assert "role" not in columns
    assert "roles" not in columns

    async with api.session() as s:
        user = (await s.execute(select(User).where(User.username == "multi01"))).scalar_one()
        assert user.roles == ["approver", "subsystem"]
        assert user.has_role("approver") and user.has_role("subsystem")
        assert not user.has_role("admin")
        assert user.is_admin is False
