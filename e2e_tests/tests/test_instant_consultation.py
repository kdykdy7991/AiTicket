"""Scenario 01 — 即时办结咨询。

分类:咨询 / 即时 / 即时办结咨询 (1102)
期望:create_ticket with is_instant_resolve=true → state=archived,
       solved_at != null, closed_at != null, resolution 非空, state_log 1 条。
"""
from __future__ import annotations

import pytest

from e2e_tests.tests import helpers
from e2e_tests.tests.helpers import ScenarioResult


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_instant_consultation(
    e2e_client, token, batch_id, result_collector
):
    scenario = "01 即时办结咨询"
    cat = helpers.find_category_by_name(e2e_client, token, "即时办结咨询")
    assert cat is not None, "未找到 leaf 分类:即时办结咨询"

    customer_name = f"E2E-即时咨询-{batch_id}"
    description = f"[E2E][{batch_id}] 请问套餐业务如何查询?"
    answer = "E2E 自动化测试:客服已即时完成解答。"
    payload = helpers.base_ticket_payload(
        customer_name=customer_name,
        description=description,
        category_id=cat["id"],
        is_instant_resolve=True,
        instant_resolution=answer,
        priority="p3_normal",
    )
    ticket = helpers.create_ticket(e2e_client, token, payload)

    assert ticket["id"] > 0, ticket
    assert ticket["state"] == "archived", ticket["state"]
    assert ticket["solved_at"] is not None, "solved_at 应非空"
    assert ticket["closed_at"] is not None, "closed_at 应非空"
    assert ticket.get("resolution") == answer, ticket

    logs = helpers.get_state_logs(e2e_client, token, ticket["id"])
    assert len(logs) >= 1, logs
    assert logs[0]["from_state"] is None and logs[0]["to_state"] == "archived", logs[0]

    # 列表里能查到
    listed = helpers.list_tickets_by_customer(e2e_client, token, customer_name)
    assert any(t["id"] == ticket["id"] for t in listed), listed

    result_collector.append(ScenarioResult(
        scenario=scenario,
        ticket_number=ticket.get("number"),
        ticket_id=ticket["id"],
        category=f"{cat['id']} {cat['name']}",
        state=ticket["state"],
        result="PASS",
        extra={"solved_at": ticket["solved_at"], "closed_at": ticket["closed_at"]},
    ))