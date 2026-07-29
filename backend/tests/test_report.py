"""报表 period 参数回归测试。

前端选自定义日期范围时会传 period=custom，后端 Query 的 pattern 曾漏掉
custom，导致 422 校验失败、前端报错。
"""


async def test_report_custom_period(client):
    """period=custom + 显式日期范围 -> 200（不再 422）。"""
    c, _dispatcher_id, _engine = client
    resp = await c.get(
        "/api/v1/stats/report",
        params={"period": "custom", "date_from": "2026-07-01", "date_to": "2026-07-29"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["date_from"] == "2026-07-01"
    assert data["date_to"] == "2026-07-29"
