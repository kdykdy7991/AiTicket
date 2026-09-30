"""Scenarios 06-09 — 业务保障 full flow (pending → open → resolved → archived)。

06 核心网系统 (2311) → 链 [软件开发组]
07 测运控系统 (2312) → 链 [测运控组]
08 卫星系统   (2313) → 链 [整星产品]
09 终端软件   (2321) → 链 [终端研发] (V0.21 自带链直达,不再父链上溯 2301)

V0.21 链语义:建单时链首部门 = skill_group = handler_skill_group,
dispatcher = 链首部门对接人(prescribe_dept),并写链快照
(dispatch_chain_steps / dispatch_step_index=0)。期望值全部从
 /routing-rules/resolve 动态取,不硬编码姓名。

完整链路:
  pending (建单,自动匹配 dispatcher / handler_skill_group)
  → open (分派 + owner=链处方默认处理人)
  → resolved (root_cause + solution)
  → archived (admin 全权限)

每场景断言责任字段与链一致,state_log 四条完整。
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
    expected_chain: list[str],
):
    cat = helpers.find_category_by_name(client, token, category_name)
    assert cat is not None, f"未找到 leaf 分类:{category_name}"

    # 期望责任从链解析动态取(V0.21 dispatch_chains)
    resp = helpers.resolve_routing(client, token, cat["id"])
    assert resp.get("matched") is True, resp
    assert resp.get("via") == "chain", resp
    assert [s["department_code"] for s in resp["chain_steps"]] == expected_chain, resp
    dept = expected_chain[0]
    expected_dispatcher_name = helpers.expected_dispatcher_name(client, token, resp)

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
    assert ticket["dispatcher_id"] == resp["dispatcher_id"], ticket
    assert ticket["dispatcher_name"] == expected_dispatcher_name, ticket
    assert ticket["skill_group_name"] == dept, ticket
    assert ticket["handler_skill_group_name"] == dept, ticket
    # 链快照已写入
    assert ticket.get("dispatch_chain_steps") == resp["chain_steps"], ticket
    assert ticket.get("dispatch_step_index") == 0, ticket

    # 2) 分派: pending → open,owner=链处方默认处理人
    owner_user = helpers.find_user_by_id(client, token, resp["owner_id"])
    assert owner_user is not None, f"链处方 owner_id={resp['owner_id']} 不存在"
    owner_id = owner_user["id"]
    after_open = helpers.patch_ticket(client, token, ticket_id, {
        "state": "open",
        "owner_id": owner_id,
    })
    after_open_detail = helpers.get_ticket_until_state(
        client, token, ticket_id, target_state="open",
    )
    assert after_open_detail["state"] == "open", after_open_detail
    assert after_open_detail["owner_name"] == owner_user["name"], after_open_detail

    # 3) 处理: open → resolved
    root_cause = f"{scenario_label}:链路告警触发条件未对齐"
    solution = f"{scenario_label}:已重新下发链路配置并回归测试"
    after_resolved = helpers.patch_ticket(client, token, ticket_id, {
        "state": "resolved",
        "root_cause": root_cause,
        "solution": solution,
    })
    after_resolved_detail = helpers.get_ticket_until_state(
        client, token, ticket_id, target_state="resolved",
    )
    assert after_resolved_detail["state"] == "resolved", after_resolved_detail
    assert after_resolved_detail["solved_at"] is not None, "resolved 应有 solved_at"
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
    after_archived_detail = helpers.get_ticket_until_state(
        client, token, ticket_id, target_state="archived",
    )
    assert after_archived_detail["state"] == "archived", after_archived_detail
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
        owner=owner_user["name"],
        result="PASS",
        extra={
            "chain": expected_chain,
            "handler_skill_group": dept,
            "transitions": [f"{a or 'None'}->{b}" for a, b in transition_chain],
        },
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_core_network_business_support(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 06 — 核心网系统 (2311) → 链 [软件开发组]。"""
    _run_business_support_scenario(
        scenario_label="06 核心网系统",
        category_name="核心网系统",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="核心网",
        expected_chain=["软件开发组"],
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_tt_and_control_business_support(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 07 — 测运控系统 (2312) → 链 [测运控组]。"""
    _run_business_support_scenario(
        scenario_label="07 测运控系统",
        category_name="测运控系统",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="测运控",
        expected_chain=["测运控组"],
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_satellite_business_support(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 08 — 卫星系统 (2313) → 链 [整星产品]。"""
    _run_business_support_scenario(
        scenario_label="08 卫星系统",
        category_name="卫星系统",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="卫星",
        expected_chain=["整星产品"],
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_terminal_software_parent_walk(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 09 — 终端软件 (2321),V0.21 自带链 [终端研发] 直达。

    老设计是父链上溯到 2301 业务保障组;V0.21 每类一条链后
    2321 直接命中自己的链,验证链优先于继承。
    """
    _run_business_support_scenario(
        scenario_label="09 终端软件(自带链直达)",
        category_name="终端软件",
        batch_id=batch_id,
        client=e2e_client, token=token,
        result_collector=result_collector,
        customer_suffix="终端软件",
        expected_chain=["终端研发"],
    )
