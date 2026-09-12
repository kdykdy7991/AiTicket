"""POC 统计接口测试（旧客服报表逻辑已下线）。"""

from helpers import run_steps


async def test_dashboard_uses_poc_states_and_scope(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 4)  # planning

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


async def test_report_and_trend_for_period(api):
    api.as_("presales01")
    ticket_id = (await api.create_ticket()).json()["data"]["id"]
    await run_steps(api, ticket_id, 9)  # closed

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
