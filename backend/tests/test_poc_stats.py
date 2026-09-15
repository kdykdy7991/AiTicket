"""POC 统计接口测试（旧客服报表逻辑已下线）。"""

from helpers import run_steps


async def test_dashboard_uses_poc_states_and_scope(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 2)  # planning

    api.as_("quality01")
    resp = await api.c.get("/api/v1/stats/dashboard")
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["total"] == 1
    assert data["open_count"] == 1
    assert data["closed_count"] == 0
    assert data["by_state"] == {"planning": 1}
    assert data["by_priority"] == {"p2_normal": 1}
    assert data["by_skill_group"] == {"系统总体": 1}
    assert data["pending_approval_count"] == 0

    # 数据范围同样生效
    api.as_("presales02")
    scoped = (await api.c.get("/api/v1/stats/dashboard")).json()["data"]
    assert scoped["total"] == 0


async def test_temporarily_resolved_derived_from_measure_and_stage(api):
    """临时解决是派生口径：有临时措施且未走到质量评审，与 verification_status 无关。"""
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]

    # 制定计划前（planning，无临时措施，质量评审之前）→ 计入处理中
    await run_steps(api, ticket_id, 2)
    api.as_("quality01")
    data = (await api.c.get("/api/v1/stats/dashboard")).json()["data"]
    assert data["processing_count"] == 1
    assert data["temporarily_resolved_count"] == 0
    assert data["resolved_count"] == 0
    assert data["by_category"] == {"processing": 1}
    # 尚无计划完成时间 → 未按时闭环率分母为 0，返回 null
    assert data["plan_eligible_count"] == 0
    assert data["overdue_closure_rate"] is None

    # 计划含临时措施，当前在 processing（质量评审之前）→ 转为临时解决
    await run_steps(api, ticket_id, 4, start=2)
    data = (await api.c.get("/api/v1/stats/dashboard")).json()["data"]
    assert data["temporarily_resolved_count"] == 1
    assert data["processing_count"] == 0
    assert data["by_category"] == {"temporary": 1}
    # 有计划完成时间（测试数据中为未来时间），未超时 → 比率 0.0 而非 null
    assert data["plan_eligible_count"] == 1
    assert data["overdue_closure_rate"] == 0.0

    # 提交分析 + 质量评审通过（已解决）后 → 两者都不再计入
    await run_steps(api, ticket_id, 6, start=4)
    data = (await api.c.get("/api/v1/stats/dashboard")).json()["data"]
    assert data["temporarily_resolved_count"] == 0
    assert data["processing_count"] == 0
    assert data["resolved_count"] == 1
    assert data["by_category"] == {"resolved": 1}
    # 闭环率 = 已解决 / 总数
    assert data["resolution_rate"] == 1.0


async def test_suspended_count_from_quality_review(api):
    """挂起 = 质量评审结论为 suspended。"""
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 5)  # 推进到待质量评审

    api.as_("quality01")
    await api.action(
        ticket_id,
        "pass_review",
        payload={
            "verification_status": "suspended",
            "verification_conclusion": "条件不足，挂起待后续复现",
            "quality_review_result": "挂起",
        },
    )
    data = (await api.c.get("/api/v1/stats/dashboard")).json()["data"]
    assert data["suspended_count"] == 1
    assert data["resolved_count"] == 0
    # 卡片与饼图同源
    assert data["by_category"] == {"suspended": 1}


async def test_report_and_trend_for_period(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 7)  # closed

    api.as_("quality01")
    today = __import__("datetime").date.today().isoformat()
    report = await api.c.get(
        "/api/v1/stats/report",
        params={"period": "custom", "date_from": today, "date_to": today},
    )
    assert report.status_code == 200, report.text
    metrics = report.json()["data"]["metrics"]
    assert metrics["new_count"] == 1
    assert metrics["closed_count"] == 1
    assert metrics["overdue_count"] == 0
    assert metrics["by_verification_status"] == {"resolved": 1}
    assert metrics["avg_closure_minutes"] is not None

    trend = await api.c.get(
        "/api/v1/stats/trend", params={"date_from": today, "date_to": today}
    )
    assert trend.status_code == 200, trend.text
    days = trend.json()["data"]["days"]
    assert len(days) == 1
    assert days[0]["new"] == 1
    assert days[0]["closed"] == 1


async def test_report_rejects_unknown_period(api):
    api.as_("quality01")
    resp = await api.c.get("/api/v1/stats/report", params={"period": "yearly"})
    assert resp.status_code == 422
