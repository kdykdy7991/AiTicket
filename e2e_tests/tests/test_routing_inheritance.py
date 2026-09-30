"""Scenario 14 — 分派链命中路径(V0.21 dispatch_chains 链优先)。

不创建临时分类/路由(避免污染 dev DB 与脆弱的 fixture teardown),
直接用现有数据验证 4 种命中路径:

14a L4 直命中:resolve 2311 (核心网系统) → 自带链 [软件开发组],
     via=chain,matched_rule_category_id=2311,dispatcher_id 非空,
     dispatcher_name=None(链路径预填只回 id,名字由详情 join)
14b L3 自带链:resolve 2322 (硬件故障) → 自带链 [售后] 直命中自身,
     不再上溯 2301(V0.21 每类一条链;父链上溯语义由后端单测覆盖)
14c L2 直命中:resolve 2301 (业务保障) → 自带链 [售后],via=chain
14d 全链路无链无规则:resolve 1101 (即时,L1=1001 咨询)→ matched=False

附加 14e:无链分类回退旧规则 — resolve 2103 (重要投诉) → 父链上溯
     命中 2101 旧 category_routing_rules(via=rule,双轨过渡)
"""
from __future__ import annotations

import pytest

from e2e_tests.tests import helpers
from e2e_tests.tests.helpers import ScenarioResult


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_parent_chain_l4_direct_hit(
    e2e_client, token, batch_id, result_collector
):
    """14a — L4 leaf 自带分派链,resolve 直命中 L4 自身(V0.21 链优先)。"""
    # 2311 核心网系统 (L4) — dispatch_chains 链 [软件开发组]
    r = helpers.resolve_routing(e2e_client, token, 2311)
    assert r.get("matched") is True, r
    assert r.get("via") == "chain", r
    assert r["matched_rule_category_id"] == 2311, (
        f"L4 命中应为 2311,实际={r.get('matched_rule_category_id')}"
    )
    assert [s["department_code"] for s in r["chain_steps"]] == ["软件开发组"], r
    assert r["dispatcher_skill_group_name"] == "软件开发组", r
    assert r["dispatcher_id"] is not None, r
    # 链路径预填只回 id,姓名由工单详情 join(dispatch_chain.py 设计)
    assert r["dispatcher_name"] is None, r

    result_collector.append(ScenarioResult(
        scenario="14a L4 直命中",
        category="2311 核心网系统 (L4)",
        state="matched-self",
        result="PASS",
        extra={
            "matched_rule_category_id": r["matched_rule_category_id"],
            "chain": [s["department_code"] for s in r["chain_steps"]],
        },
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_parent_chain_l3_walks_to_l2(
    e2e_client, token, batch_id, result_collector
):
    """14b — L3 自带链直命中自身(2322 硬件故障链 [售后]),不上溯 2301。

    V0.21 每个分类一条链:2322 自己的链先精确命中,父链上溯只在
    自身无链时发生(语义由 backend dispatch_chain 单测覆盖)。
    """
    r = helpers.resolve_routing(e2e_client, token, 2322)
    assert r.get("matched") is True, r
    assert r.get("via") == "chain", r
    assert r["matched_rule_category_id"] == 2322, (
        f"2322 应命中自身链,实际={r.get('matched_rule_category_id')}"
    )
    assert [s["department_code"] for s in r["chain_steps"]] == ["售后"], r
    assert r["dispatcher_skill_group_name"] == "售后", r

    result_collector.append(ScenarioResult(
        scenario="14b L3 自带链直命中",
        category="2322 硬件故障 (L3)",
        state="matched-self",
        result="PASS",
        extra={"matched_rule_category_id": r["matched_rule_category_id"]},
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_parent_chain_l2_direct_hit(
    e2e_client, token, batch_id, result_collector
):
    """14c — L2 自带链,resolve 直命中 L2 自身。"""
    # 2301 业务保障 (L2) — dispatch_chains 链 [售后]
    r = helpers.resolve_routing(e2e_client, token, 2301)
    assert r.get("matched") is True, r
    assert r.get("via") == "chain", r
    assert r["matched_rule_category_id"] == 2301, r
    assert r["dispatcher_skill_group_name"] == "售后", r

    result_collector.append(ScenarioResult(
        scenario="14c L2 直命中",
        category="2301 业务保障 (L2)",
        state="matched-self",
        result="PASS",
        extra={"matched_rule_category_id": r["matched_rule_category_id"]},
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_parent_chain_all_miss(
    e2e_client, token, batch_id, result_collector
):
    """14d — 全链路无链无规则(1101 即时,L1=1001 咨询)→ matched=False。"""
    r = helpers.resolve_routing(e2e_client, token, 1101)
    assert r.get("matched") is False, f"1101 不应命中:{r}"
    assert r.get("matched_rule_category_id") in (None, 0, ""), r

    result_collector.append(ScenarioResult(
        scenario="14d 全链路无 rule",
        category="1101 即时 (L2)",
        state="unmatched",
        result="PASS",
        extra={"resolve_response": r},
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_parent_chain_complaint_l3_to_l2(
    e2e_client, token, batch_id, result_collector
):
    """14e — 无链分类回退旧规则:2103 (重要投诉) → 父链上溯命中 2101 旧规则。

    2103 未配链(V0.21 只给 2102 一般投诉配链)→ 双轨过渡走旧
    category_routing_rules 的 parent walk,via=rule。
    """
    r = helpers.resolve_routing(e2e_client, token, 2103)
    assert r.get("matched") is True, r
    assert r.get("via") == "rule", r
    assert r["matched_rule_category_id"] == 2101, (
        f"2103 应匹配 2101,实际={r.get('matched_rule_category_id')}"
    )
    assert r["dispatcher_name"] == "服务投诉协调人", r

    result_collector.append(ScenarioResult(
        scenario="14e 投诉 L3 退回 L2 命中",
        category="2103 重要投诉 (L3)",
        state="matched-via-parent",
        result="PASS",
        extra={"matched_via": "2101", "matched_rule_category_id": r["matched_rule_category_id"]},
    ))