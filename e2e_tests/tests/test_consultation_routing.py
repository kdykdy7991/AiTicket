"""Scenarios 02 + 03 — 非即时咨询的责任路由自动匹配。

02 品牌合作 (1202):
    期待 dispatcher_skill_group = 品牌传播与大客户,dispatcher = 钟梦茜
03 产品使用/参数咨询 (1203):
    期待 dispatcher_skill_group = 产品,dispatcher = 张朝娟

依赖:Phase 9 seed rename + V2_MISSING_LEAF_RULES。
本测试只验"创建瞬间是否自动匹配成功",不驱状态机流转。
"""
from __future__ import annotations

import pytest

from e2e_tests.tests import helpers
from e2e_tests.tests.helpers import ScenarioResult


def _create_and_assert_routing(
    *,
    scenario_label: str,
    batch_id: str,
    client,
    token,
    category_name: str,
    expected_sg_name: str,
    expected_dispatcher_name: str,
    short_label: str,
    result_collector: list,
    extra_customer_suffix: str,
):
    cat = helpers.find_category_by_name(client, token, category_name)
    assert cat is not None, f"未找到 leaf 分类:{category_name}"

    # 显式不填 dispatcher/owner → 走 create_ticket 自动匹配链路
    customer_name = f"E2E-{extra_customer_suffix}-{batch_id}"
    description = f"[E2E][{batch_id}] {scenario_label} 自动匹配责任路由"
    payload = helpers.base_ticket_payload(
        customer_name=customer_name,
        description=description,
        category_id=cat["id"],
        priority="p3_normal",
    )
    ticket = helpers.create_ticket(client, token, payload)

    # 关键断言:自动匹配到正确的 dispatcher / skill_group
    assert ticket["dispatcher_id"] is not None, ticket
    assert ticket["skill_group_name"] == expected_sg_name, (
        f"{scenario_label}: skill_group_name 不匹配 "
        f"actual={ticket.get('skill_group_name')!r}"
    )
    assert ticket["dispatcher_name"] == expected_dispatcher_name, (
        f"{scenario_label}: dispatcher_name 不匹配 "
        f"actual={ticket.get('dispatcher_name')!r}"
    )
    # 非即时 → pending
    assert ticket["state"] == "pending", ticket["state"]

    logs = helpers.get_state_logs(client, token, ticket["id"])
    assert len(logs) >= 1, logs
    assert logs[0]["from_state"] is None and logs[0]["to_state"] == "pending", logs[0]

    # 列表可查
    listed = helpers.list_tickets_by_customer(client, token, customer_name)
    assert any(t["id"] == ticket["id"] for t in listed), listed

    result_collector.append(ScenarioResult(
        scenario=scenario_label,
        ticket_number=ticket.get("number"),
        ticket_id=ticket["id"],
        category=f"{cat['id']} {cat['name']}",
        state=ticket["state"],
        dispatcher=expected_dispatcher_name,
        owner=ticket.get("owner_name") or "(未指定)",
        result="PASS",
        extra={
            "skill_group_name": expected_sg_name,
            "dispatcher_id": ticket["dispatcher_id"],
        },
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_brand_collaboration_routing(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 02 — 品牌合作 (1202) → 品牌传播与大客户 / 钟梦茜。"""
    _create_and_assert_routing(
        scenario_label="02 品牌合作",
        batch_id=batch_id,
        client=e2e_client,
        token=token,
        category_name="品牌合作",
        expected_sg_name="品牌传播与大客户",
        expected_dispatcher_name="钟梦茜",
        short_label="品牌合作",
        result_collector=result_collector,
        extra_customer_suffix="品牌合作",
    )


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_product_consultation_routing(
    e2e_client, token, batch_id, result_collector
):
    """Scenario 03 — 产品使用/参数咨询 (1203) → 产品 / 张朝娟。"""
    _create_and_assert_routing(
        scenario_label="03 产品使用/参数咨询",
        batch_id=batch_id,
        client=e2e_client,
        token=token,
        category_name="产品使用/参数咨询",
        expected_sg_name="产品",
        expected_dispatcher_name="张朝娟",
        short_label="产品咨询",
        result_collector=result_collector,
        extra_customer_suffix="产品咨询",
    )