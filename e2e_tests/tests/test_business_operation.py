"""Scenarios 04 + 05 — 业务运营 (套餐变更 / 业财对账) full flow。

V0.21 链:
  2203 套餐变更 → 链 [市场生态部, 业务支撑组] (审核→执行,两步)
  2204 业财对账 → 客服指定销售 → 销售选公司及财务人员

建单落链首部门为 skill_group/handler_skill_group,dispatcher=链首
部门对接人;期望值从 /routing-rules/resolve 动态取,不硬编码姓名。

流转链路: pending → open (分派,owner=链处方默认处理人)
        → resolved (写 root_cause + solution) → state_log 校验

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
    assert ticket["dispatcher_id"] == resp["dispatcher_id"], ticket
    assert ticket["dispatcher_name"] == expected_dispatcher_name, ticket
    assert ticket["skill_group_name"] == dept, ticket
    assert ticket["handler_skill_group_name"] == dept, ticket
    assert ticket["dispatcher_id"] is not None, ticket
    # 两步链快照已写入,起始步 0
    assert ticket.get("dispatch_chain_steps") == resp["chain_steps"], ticket
    assert ticket.get("dispatch_step_index") == 0, ticket
    # owner 不在 create 时被写入(状态机规则见下)

    # 2) 分派: pending → open,owner=链处方默认处理人
    owner_user = helpers.find_user_by_id(client, token, resp["owner_id"])
    assert owner_user is not None, f"链处方 owner_id={resp['owner_id']} 不存在"
    owner_id = owner_user["id"]
    after_open = helpers.patch_ticket(client, token, ticket_id, {
        "state": "open",
        "owner_id": owner_id,
    })
    assert after_open["owner_id"] == owner_id, after_open
    after_open_detail = helpers.get_ticket_until_state(
        client, token, ticket_id, target_state="open",
    )
    assert after_open_detail["state"] == "open", after_open_detail
    assert after_open_detail["owner_name"] == owner_user["name"], after_open_detail

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
        dispatcher=expected_dispatcher_name,
        owner=owner_user["name"],
        result="PASS",
        extra={
            "chain": expected_chain,
            "transitions": [f"{a or 'None'}->{b}" for a, b in transition_chain],
        },
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_plan_change_business_operation(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 04 — 套餐变更 (2203) → 链 [市场生态部, 业务支撑组] → resolved。"""
    _run_business_op_scenario(
        scenario_label="04 套餐变更",
        category_name="套餐变更",
        batch_id=batch_id,
        client=e2e_client,
        token=token,
        result_collector=result_collector,
        customer_suffix="套餐变更",
        expected_chain=["市场生态部", "业务支撑组"],
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_finance_reconciliation_business_operation(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 05 — 销售填写对账信息并指定时空道宇财务姜敏。"""
    import json
    import os

    cat = helpers.find_category_by_name(e2e_client, token, "业财对账")
    assert cat is not None
    users = helpers.list_users(e2e_client, token)
    sales = next(user for user in users if user["name"] == "陈可意")
    finance = next(user for user in users if user["name"] == "姜敏")
    customer_name = f"E2E-业财对账-{batch_id}"
    payload = helpers.base_ticket_payload(
        customer_name=customer_name, description="业财对账，请销售核对后交财务",
        category_id=cat["id"], extra={"sales_owner_id": sales["id"]},
    )
    ticket = helpers.create_ticket(e2e_client, token, payload)
    assert ticket["state"] == "open" and ticket["owner_id"] == sales["id"]
    login = e2e_client.post(
        f"{helpers.API_BASE}/api/v1/auth/login",
        json={"username": "chenkeyi", "password": os.environ.get("E2E_SALES_PASSWORD", "skdy123")},
    )
    login.raise_for_status()
    sales_token = login.json()["access_token"]
    detail = helpers.get_ticket(e2e_client, sales_token, ticket["id"])
    form = detail["current_form"]
    assert form["code"] == "reconciliation_sales_v1"
    result = e2e_client.post(
        f"{helpers.API_BASE}/api/v1/tickets/{ticket['id']}/node-submit",
        headers=helpers.auth_headers(sales_token),
        data={"payload": json.dumps({
            "form_definition_id": form["form_definition_id"], "form_version": form["version"],
            "expected_category_id": cat["id"], "expected_department_id": detail["skill_group_id"],
            "expected_dispatch_step_index": 0, "expected_state": "open",
            "values": {
                "reconciliation_customer_name": customer_name,
                "finance_company": "时空道宇", "finance_person": "姜敏",
                "processing_opinion": "销售已核对，请财务处理",
            },
        }, ensure_ascii=False)},
    )
    result.raise_for_status()
    handed_off = result.json()["data"]
    assert handed_off["state"] == "open"
    assert handed_off["owner_id"] == finance["id"]
    assert handed_off["dispatch_step_index"] == 1
    result_collector.append(ScenarioResult(
        scenario="05 业财对账", ticket_number=ticket.get("number"), ticket_id=ticket["id"],
        category=f"{cat['id']} {cat['name']}", state=handed_off["state"],
        dispatcher="陈可意", owner="姜敏", result="PASS",
        extra={"chain": ["销售", "财务"]},
    ))
