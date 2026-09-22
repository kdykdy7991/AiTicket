"""Scenarios 06-09 — 业务保障 full flow (pending → open → resolved → archived)。

06 核心网系统 (2311) → 核心网组 / 核心网处理人
07 测运控系统 (2312) → 测运控组 / 测运控处理人
08 卫星系统   (2313) → 卫星组   / 卫星处理人
09 终端软件   (2321) → 父链上溯到 2301 业务保障组 / 业务保障处理人
                  (2321 在 dev DB 没有 leaf 路由,验证父链继承)

完整链路:
  pending (建单,自动匹配 dispatcher / handler_skill_group)
  → open (分派 + owner_id)
  → resolved (root_cause + solution)
  → archived (admin 全权限)

每场景断言 dispatcher / handler_skill_group / owner 与 routing rule 一致,
state_log 四条完整。
"""
from __future__ import annotations

import pytest

from e2e_tests.tests import helpers
from e2e_tests.tests.helpers import ScenarioResult


def _run_business_support_scenario(
    *,
    scenario_label: str,
    category_name: str,
    batch_id: str,
    client,
    token,
    result_collector: list,
    customer_suffix: str,
    expected_sg_name: str,
    expected_dispatcher_name: str,
    expected_handler_sg_name: str,
    expected_owner_name: str,
):
    cat = helpers.find_category_by_name(client, token, category_name)
    assert cat is not None, f"未找到 leaf 分类:{category_name}"

    customer_name = f"E2E-{customer_suffix}-{batch_id}"
    description = f"[E2E][{batch_id}] {scenario_label} 业务保障全流程"

    # 1) 建单 (pending)
    payload = helpers.base_ticket_payload(
        customer_name=customer_name,
        description=description,
        category_id=cat["id"],
        priority="p2_important",  # 业务保障用 important 优先级更接近真实
    )
    ticket = helpers.create_ticket(client, token, payload)
    ticket_id = ticket["id"]
    assert ticket["state"] == "pending", ticket["state"]
    assert ticket["dispatcher_name"] == expected_dispatcher_name, ticket
    assert ticket["skill_group_name"] == expected_sg_name, ticket
    assert ticket["handler_skill_group_name"] == expected_handler_sg_name, ticket

    # 2) 分派: pending → open,owner 按期望查
    owner_user = helpers.find_user_by_name(client, token, expected_owner_name)
    assert owner_user is not None, f"未找到 owner:{expected_owner_name}"
    owner_id = owner_user["id"]
    after_open = helpers.patch_ticket(client, token, ticket_id, {
        "state": "open",
        "owner_id": owner_id,
    })
    assert after_open["state"] == "open", after_open
    after_open_detail = helpers.get_ticket(client, token, ticket_id)
    assert after_open_detail["owner_name"] == expected_owner_name, after_open_detail

    # 3) 处理: open → resolved
    root_cause = f"{scenario_label}:链路告警触发条件未对齐"
    solution = f"{scenario_label}:已重新下发链路配置并回归测试"
    after_resolved = helpers.patch_ticket(client, token, ticket_id, {
        "state": "resolved",
        "root_cause": root_cause,
        "solution": solution,
    })
    assert after_resolved["state"] == "resolved", after_resolved
    assert after_resolved["solved_at"] is not None, "resolved 应有 solved_at"
    after_resolved_detail = helpers.get_ticket(client, token, ticket_id)
    assert after_resolved_detail["root_cause"] == root_cause, after_resolved_detail
    assert after_resolved_detail["solution"] == solution, after_resolved_detail

    # 4) 归档: resolved → archived
    after_archived = helpers.patch_ticket(client, token, ticket_id, {
        "state": "archived",
        "archive_notes": f"{scenario_label}:归档备注(E2E 自动化)",
        "is_callbacked": True,
        "callback_required": False,
        "callback_details": "E2E 自动化:无需回访",
    })
    assert after_archived["state"] == "archived", after_archived
    after_archived_detail = helpers.get_ticket(client, token, ticket_id)
    assert after_archived_detail["closed_at"] is not None, "archived 应有 closed_at"

    # 5) state_log 四条完整 — 轮询避免偶发 stale-read
    logs = helpers.get_state_logs_until(
        client, token, ticket_id,
        predicate=lambda rows: any(
            (r["from_state"] == "resolved" and r["to_state"] == "archived") for r in rows
        ),
    )
    transition_chain = [(l["from_state"], l["to_state"]) for l in logs]
    assert (None, "pending") in transition_chain, logs
    assert ("pending", "open") in transition_chain, logs
    assert ("open", "resolved") in transition_chain, logs
    assert ("resolved", "archived") in transition_chain, logs

    result_collector.append(ScenarioResult(
        scenario=scenario_label,
        ticket_number=ticket.get("number"),
        ticket_id=ticket_id,
        category=f"{cat['id']} {cat['name']}",
        state=after_archived["state"],
        dispatcher=expected_dispatcher_name,
        owner=expected_owner_name,
        result="PASS",
        extra={
            "dispatcher_skill_group": expected_sg_name,
            "handler_skill_group": expected_handler_sg_name,
            "transitions": [f"{a or 'None'}->{b}" for a, b in transition_chain],
        },
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_core_network_business_support(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 06 — 核心网系统 (2311) → 核心网组 / 核心网处理人。"""
    _run_business_support_scenario(
        scenario_label="06 核心网系统",
        category_name="核心网系统",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="核心网",
        expected_sg_name="业务保障组",
        expected_dispatcher_name="业务保障协调人",
        expected_handler_sg_name="核心网组",
        expected_owner_name="核心网处理人",
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_tt_and_control_business_support(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 07 — 测运控系统 (2312) → 测运控组 / 测运控处理人。"""
    _run_business_support_scenario(
        scenario_label="07 测运控系统",
        category_name="测运控系统",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="测运控",
        expected_sg_name="业务保障组",
        expected_dispatcher_name="业务保障协调人",
        expected_handler_sg_name="测运控组",
        expected_owner_name="测运控处理人",
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_satellite_business_support(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 08 — 卫星系统 (2313) → 卫星组 / 卫星处理人。"""
    _run_business_support_scenario(
        scenario_label="08 卫星系统",
        category_name="卫星系统",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="卫星",
        expected_sg_name="业务保障组",
        expected_dispatcher_name="业务保障协调人",
        expected_handler_sg_name="卫星组",
        expected_owner_name="卫星处理人",
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_terminal_software_parent_walk(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 09 — 终端软件 (2321),无 leaf 路由 → 父链上溯到 2301。

    期望 dispatcher_skill_group=业务保障组、owner=业务保障处理人(2311/2312/2313
    有独立 routing rule,所以这一例是验证父链继承路径而非 leaf 直匹配)。
    """
    _run_business_support_scenario(
        scenario_label="09 终端软件(父链上溯)",
        category_name="终端软件",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="终端软件",
        expected_sg_name="业务保障组",
        expected_dispatcher_name="业务保障协调人",
        expected_handler_sg_name="业务保障组",
        expected_owner_name="业务保障处理人",
    )