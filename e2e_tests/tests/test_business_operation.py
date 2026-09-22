"""Scenarios 04 + 05 — 业务运营 (套餐变更 / 业财对账) full flow。

2203 套餐变更 + 2204 业财对账:走父链 2201 业务运营组。
期望 dispatcher=业务运营协调人 (id=201) / sg=业务运营组 (id=101) /
owner=业务运营处理人 (id=210)。

流转链路: pending → open (分派,owner=210) → resolved (写 root_cause + solution)
        → 可选 archived (客服归档)

admin 走全权限路径,所以一条 token 即可。
"""
from __future__ import annotations

import pytest

from e2e_tests.tests import helpers
from e2e_tests.tests.helpers import ScenarioResult


def _run_business_op_scenario(
    *,
    scenario_label: str,
    category_name: str,
    batch_id: str,
    client,
    token,
    result_collector: list,
    customer_suffix: str,
):
    cat = helpers.find_category_by_name(client, token, category_name)
    assert cat is not None, f"未找到 leaf 分类:{category_name}"

    customer_name = f"E2E-{customer_suffix}-{batch_id}"
    description = f"[E2E][{batch_id}] {scenario_label} 全流程责任路由+状态流转"

    # 1) 建单 (pending) — 不填 dispatcher/owner,触发自动匹配
    payload = helpers.base_ticket_payload(
        customer_name=customer_name,
        description=description,
        category_id=cat["id"],
        priority="p3_normal",
    )
    ticket = helpers.create_ticket(client, token, payload)
    ticket_id = ticket["id"]
    assert ticket["state"] == "pending", ticket["state"]
    assert ticket["dispatcher_name"] == "业务运营协调人", ticket
    assert ticket["skill_group_name"] == "业务运营组", ticket
    assert ticket["dispatcher_id"] is not None, ticket
    # owner 不在 create 时被写入(状态机规则见下)

    # 2) 分派: pending → open,同时设置 owner_id=业务运营处理人
    owner_user = helpers.find_user_by_name(client, token, "业务运营处理人")
    assert owner_user is not None, "未找到 owner:业务运营处理人"
    owner_id = owner_user["id"]
    after_open = helpers.patch_ticket(client, token, ticket_id, {
        "state": "open",
        "owner_id": owner_id,
    })
    assert after_open["state"] == "open", after_open
    assert after_open["owner_id"] == owner_id, after_open
    # PATCH 响应可能不包含 joined owner_name;重新 GET 拿详情
    after_open_detail = helpers.get_ticket(client, token, ticket_id)
    assert after_open_detail["owner_name"] == "业务运营处理人", after_open_detail

    # 3) 处理: open → resolved (写 root_cause / solution)
    root_cause = f"{scenario_label}:客户订单系统计费参数配置错误"
    solution = f"{scenario_label}:已重新校准计费参数,补发差额"
    after_resolved = helpers.patch_ticket(client, token, ticket_id, {
        "state": "resolved",
        "root_cause": root_cause,
        "solution": solution,
    })
    assert after_resolved["state"] == "resolved", after_resolved
    assert after_resolved["root_cause"] == root_cause, after_resolved
    assert after_resolved["solution"] == solution, after_resolved
    assert after_resolved["solved_at"] is not None, "resolved 应有 solved_at"

    # 4) state_log 校验: None→pending→open→resolved 三条
    logs = helpers.get_state_logs_until(
        client, token, ticket_id,
        predicate=lambda rows: any(
            (r["from_state"] == "open" and r["to_state"] == "resolved") for r in rows
        ),
    )
    transition_chain = [(l["from_state"], l["to_state"]) for l in logs]
    assert (None, "pending") in transition_chain, logs
    assert ("pending", "open") in transition_chain, logs
    assert ("open", "resolved") in transition_chain, logs

    # 列表可查
    listed = helpers.list_tickets_by_customer(client, token, customer_name)
    assert any(t["id"] == ticket_id for t in listed), listed

    result_collector.append(ScenarioResult(
        scenario=scenario_label,
        ticket_number=ticket.get("number"),
        ticket_id=ticket_id,
        category=f"{cat['id']} {cat['name']}",
        state=after_resolved["state"],
        dispatcher="业务运营协调人",
        owner="业务运营处理人",
        result="PASS",
        extra={
            "transitions": [f"{a or 'None'}->{b}" for a, b in transition_chain],
        },
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_plan_change_business_operation(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 04 — 套餐变更 (2203) → 业务运营组 / 业务运营协调人 → resolved。"""
    _run_business_op_scenario(
        scenario_label="04 套餐变更",
        category_name="套餐变更",
        batch_id=batch_id,
        client=e2e_client,
        token=token,
        result_collector=result_collector,
        customer_suffix="套餐变更",
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_finance_reconciliation_business_operation(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 05 — 业财对账 (2204) → 业务运营组 / 业务运营协调人 → resolved。"""
    _run_business_op_scenario(
        scenario_label="05 业财对账",
        category_name="业财对账",
        batch_id=batch_id,
        client=e2e_client,
        token=token,
        result_collector=result_collector,
        customer_suffix="业财对账",
    )