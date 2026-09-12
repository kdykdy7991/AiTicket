"""列表筛选、导出字段与人员/分系统元数据接口测试（对应 BE-07 / BE-08）。"""

from datetime import date, timedelta

from helpers import run_steps


async def _make_tickets(api, count: int = 2):
    """建 count 条问题，第一条推进到 planning，第二条停在待审批。"""
    api.as_("presales01")
    ids = []
    for index in range(count):
        resp = await api.create_ticket(title=f"POC 问题-{index + 1}")
        assert resp.status_code == 201, resp.text
        ids.append(resp.json()["data"]["id"])
    if count >= 2:
        await run_steps(api, ids[0], 4)  # planning，分系统=系统总体，责任人=subsystem01
        # 给第一条填上计划完成时间，用于验证 planned_asc 排序与逾期筛选
        api.as_("subsystem01")
        resp = await api.c.patch(
            f"/api/v1/tickets/{ids[0]}",
            json={"planned_completion_at": "2026-12-31T18:00:00+08:00"},
        )
        assert resp.status_code == 200, resp.text
    return ids


async def test_list_filters(api):
    first, second = await _make_tickets(api)
    today = date.today().isoformat()
    api.as_("quality01")

    async def listed(**params):
        resp = await api.c.get("/api/v1/tickets", params=params)
        assert resp.status_code == 200, resp.text
        return [t["id"] for t in resp.json()["data"]]

    # 状态：单值与多值
    assert await listed(state="planning") == [first]
    assert sorted(await listed(state=["planning", "pending_approval"])) == sorted([first, second])

    # 优先级 / 分系统 / 责任人
    assert await listed(priority="p2_normal") == [first, second]
    assert await listed(skill_group_id=api.sg("系统总体")) == [first]
    assert await listed(responsible_user_id=api.uid("subsystem01")) == [first]
    assert await listed(responsible_user_id=api.uid("approver01")) == [second]

    # 关键词（命中标题）
    assert await listed(keyword="问题-2") == [second]

    # 创建时间区间
    assert await listed(date_from=today, date_to=today) == [first, second]
    yesterday = (date.today() - timedelta(days=1)).isoformat()
    assert await listed(date_to=yesterday) == []

    # 逾期过滤（计划完成时间在 2026-12-31，当前未逾期）
    assert await listed(is_overdue="true") == []
    assert sorted(await listed(is_overdue="false")) == sorted([first, second])

    # 排序：计划完成时间升序时，未填计划的问题排在最后
    resp = await api.c.get("/api/v1/tickets", params={"sort": "planned_asc"})
    assert [t["id"] for t in resp.json()["data"]] == [first, second]

    # 分页元数据
    resp = await api.c.get("/api/v1/tickets", params={"page": 1, "page_size": 1})
    body = resp.json()
    assert len(body["data"]) == 1
    assert body["pagination"]["total"] == 2
    assert body["pagination"]["total_pages"] == 2


async def test_list_filter_rejects_bad_params(api):
    await _make_tickets(api, count=1)
    api.as_("quality01")

    for params in (
        {"sort": "unknown"},
        {"date_from": "2026/09/01"},
        {"verification_status": "done"},
        {"page": 0},
        {"page_size": 1000},
    ):
        resp = await api.c.get("/api/v1/tickets", params=params)
        assert resp.status_code == 422, f"{params} 应被拒绝：{resp.status_code}"


async def test_export_contains_poc_tracking_columns(api):
    await _make_tickets(api, count=1)
    api.as_("quality01")
    resp = await api.c.get("/api/v1/tickets/export")
    assert resp.status_code == 200, resp.text
    header = resp.text.lstrip("\ufeff").splitlines()[0]
    assert header.split(",") == [
        "问题编号",
        "问题名称",
        "客户名称",
        "产品线",
        "问题级别",
        "问题类型",
        "发生时间",
        "当前阶段",
        "当前责任角色",
        "当前责任人",
        "分系统",
        "计划完成时间",
        "是否逾期",
        "验证状态",
        "缺陷ID",
        "SVN路径",
        "创建人",
        "创建时间",
        "闭环时间",
    ]


async def test_metadata_endpoints_for_role_selectors(api):
    api.as_("taskforce01")

    approvers = (await api.c.get("/api/v1/users", params={"role": "approver"})).json()["data"]
    # 多角色用户（同时是批准人）也会出现在这个选择器里
    assert [u["name"] for u in approvers] == ["邱庆举", "备用批准人", "多角色-邱庆举"]
    assert all("approver" in u["roles"] for u in approvers)
    # 非管理员只拿到流程需要的最小字段
    assert set(approvers[0]) == {"id", "username", "name", "roles", "skill_groups", "is_active"}

    owners = (
        await api.c.get(
            "/api/v1/users",
            params={"role": "subsystem", "skill_group_id": api.sg("卫星平台")},
        )
    ).json()["data"]
    assert [u["name"] for u in owners] == ["卢翔"]
    assert owners[0]["skill_groups"] == [{"id": api.sg("卫星平台"), "name": "卫星平台"}]

    # 旧角色筛选被拒绝
    for legacy in ("agent", "handler", "dispatcher"):
        resp = await api.c.get("/api/v1/users", params={"role": legacy})
        assert resp.status_code == 422

    groups = (await api.c.get("/api/v1/skill-groups")).json()["data"]
    assert len(groups) == 5

    meta = (await api.c.get("/api/v1/meta/poc-workflow")).json()["data"]
    assert meta["states"] == [
        "pending_approval",
        "pending_confirmation",
        "pending_routing",
        "pending_acceptance",
        "planning",
        "pending_plan_confirmation",
        "processing",
        "pending_quality_review",
        "pending_defect_registration",
        "closed",
        "returned",
        "cancelled",
    ]
    assert meta["priorities"] == ["p0_blocker", "p1_critical", "p2_normal", "p3_low"]
    assert meta["terminal_states"] == ["closed", "cancelled"]
    assert "admin" not in meta["selectable_roles"]


async def test_legacy_metadata_endpoints_return_410(api):
    api.as_("admin")
    for path in (
        f"/api/v1/skill-groups/{api.sg('系统总体')}/dispatchers",
        f"/api/v1/skill-groups/{api.sg('系统总体')}/handlers",
    ):
        resp = await api.c.get(path)
        assert resp.status_code == 410, resp.text
        assert "已下线" in resp.text
