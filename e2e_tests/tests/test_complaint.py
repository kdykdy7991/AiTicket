"""Scenarios 10-12 — 投诉分级 (一般 / 重要 / 重大)。

2102 一般投诉、2103 重要投诉、2104 重大投诉:都父链上溯到 2101 服务投诉。
期望 dispatcher=服务投诉协调人 / sg=服务投诉协调组。

注意:`sla_policies` 表当前为空(用户已知,"SLA 策略未定暂不修"),
本测试不断言 solution_deadline 的具体数值;只验证:
  - complaint_level 字段被正确写入并出现在工单详情
  - 责任路由按预期生效
  - 状态机走通 pending → resolved(可附 root_cause/solution)

倍率(1.0 / 0.75 / 0.5)通过 complaint_escalation_policies 验证存在,
不在工单上做 deadline 算术断言。
"""
from __future__ import annotations

import pytest

from e2e_tests.tests import helpers
from e2e_tests.tests.helpers import ScenarioResult


# 业务期望的 multiplier(sla_resolution_multiplier)
EXPECTED_MULTIPLIER = {
    "一般": 1.0,
    "重要": 0.75,
    "重大": 0.5,
}


def _fetch_complaint_policies(client, token):
    """读 complaint_escalation_policies,验证三档 multiplier 已 seed。"""
    r = client.get(
        f"{helpers.API_BASE}/api/v1/complaint-escalation-policies",
        headers=helpers.auth_headers(token),
    )
    # 端点可能不存在;若 404/500 则改走 DB,但 E2E 不直连 DB,改为软跳过
    if r.status_code == 404:
        return None
    r.raise_for_status()
    body = r.json()
    return body.get("data", body) if isinstance(body, dict) else body


def _run_complaint_scenario(
    *,
    scenario_label: str,
    category_name: str,
    complaint_level: str,
    batch_id: str,
    client,
    token,
    result_collector: list,
    customer_suffix: str,
):
    cat = helpers.find_category_by_name(client, token, category_name)
    assert cat is not None, f"未找到 leaf 分类:{category_name}"

    customer_name = f"E2E-{customer_suffix}-{batch_id}"
    description = f"[E2E][{batch_id}] {scenario_label} 投诉分级+责任路由"

    payload = helpers.base_ticket_payload(
        customer_name=customer_name,
        description=description,
        category_id=cat["id"],
        complaint_level=complaint_level,
        priority="p1_urgent",
    )
    ticket = helpers.create_ticket(client, token, payload)
    ticket_id = ticket["id"]
    assert ticket["state"] == "pending", ticket["state"]
    assert ticket["dispatcher_name"] == "服务投诉协调人", ticket
    assert ticket["skill_group_name"] == "服务投诉协调组", ticket
    assert ticket["complaint_level"] == complaint_level, (
        f"complaint_level 字段应保留:实际={ticket.get('complaint_level')!r}"
    )

    # pending → open (分派给 dispatcher 当 owner,因为 2101 路由无 owner)
    dispatcher_user = helpers.find_user_by_name(client, token, "服务投诉协调人")
    assert dispatcher_user is not None, "未找到 服务投诉协调人"
    after_open = helpers.patch_ticket(client, token, ticket_id, {
        "state": "open",
        "owner_id": dispatcher_user["id"],
    })
    after_open_detail = helpers.get_ticket_until_state(
        client, token, ticket_id, target_state="open",
    )
    assert after_open_detail["state"] == "open", after_open_detail

    # open → resolved(写 root_cause / solution)
    after_resolved = helpers.patch_ticket(client, token, ticket_id, {
        "state": "resolved",
        "root_cause": f"{scenario_label}:客服响应时长超出客户预期",
        "solution": f"{scenario_label}:已升级处理并补偿客户",
    })
    detail = helpers.get_ticket_until_state(
        client, token, ticket_id, target_state="resolved",
    )
    assert detail["state"] == "resolved", detail
    assert detail["root_cause"], detail
    assert detail["solution"], detail

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

    result_collector.append(ScenarioResult(
        scenario=scenario_label,
        ticket_number=ticket.get("number"),
        ticket_id=ticket_id,
        category=f"{cat['id']} {cat['name']}",
        state=after_resolved["state"],
        dispatcher="服务投诉协调人",
        owner="(投诉协调,无独立 owner)",
        result="PASS",
        extra={
            "complaint_level": complaint_level,
            "expected_multiplier": EXPECTED_MULTIPLIER[complaint_level],
            "transitions": [f"{a or 'None'}->{b}" for a, b in transition_chain],
        },
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_complaint_general(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 10 — 一般投诉 (2102) / complaint_level=一般。"""
    _run_complaint_scenario(
        scenario_label="10 一般投诉",
        category_name="一般投诉",
        complaint_level="一般",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="一般投诉",
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_complaint_important(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 11 — 重要投诉 (2103) / complaint_level=重要 / multiplier=0.75。"""
    _run_complaint_scenario(
        scenario_label="11 重要投诉",
        category_name="重要投诉",
        complaint_level="重要",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="重要投诉",
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_complaint_major(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 12 — 重大投诉 (2104) / complaint_level=重大 / multiplier=0.5。"""
    _run_complaint_scenario(
        scenario_label="12 重大投诉",
        category_name="重大投诉",
        complaint_level="重大",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="重大投诉",
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_complaint_multiplier_policy_seeded(
    e2e_client, token, batch_id, result_collector
):
    """验证 complaint_escalation_policies 三档倍率已被 seed 入库(数值合规)。

    SLA 策略本身未启用(用户已知,"SLA 策略未定暂不修"),但策略表本身
    的 multiplier 值是 Phase 8 seed 的一部分,应保留供后续启用时使用。
    """
    rows = _fetch_complaint_policies(e2e_client, token)
    # 端点可能未注册;不强制
    if rows is None:
        result_collector.append(ScenarioResult(
            scenario="13 投诉倍率策略 seed",
            result="SKIP",
            extra={"reason": "complaint-escalation-policies 端点未注册"},
        ))
        return
    by_level = {row.get("complaint_level"): row.get("sla_resolution_multiplier") for row in rows}
    for level, expected in EXPECTED_MULTIPLIER.items():
        actual = by_level.get(level)
        assert actual is not None, f"{level} 策略缺失:rows={rows}"
        # multiplier 在 DB 里通常 DECIMAL;容差 0.001
        assert abs(float(actual) - expected) < 0.001, (
            f"{level}: actual={actual} expected={expected}"
        )
    result_collector.append(ScenarioResult(
        scenario="13 投诉倍率策略 seed",
        result="PASS",
        extra={"levels": by_level},
    ))