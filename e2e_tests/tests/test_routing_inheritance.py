"""Scenario 14 — 父链上溯(resolve_rule 沿 parent_id 上溯查找)。

不创建临时分类/路由(避免污染 dev DB 与脆弱的 fixture teardown),
直接用现有数据验证 4 种继承路径:

14a L4 直命中:resolve 2311 (核心网系统) → matched_rule_category_id=2311
14b L4 退回 L3 → 沿链未命中:resolve 2322 (硬件故障,无 leaf 规则)→
     父链走完也找不到 rule(L3=2321 终端软件无 rule,L2=2301 业务保障有 rule
     但 2322.parent=2301 而非 2310 → 实际 2322 走父链到 2301 命中;
     业务保障组的规则命中 L3 leaf 2322 即"跨级命中")
14c L2 直命中:resolve 2301 (业务保障) → matched_rule_category_id=2301
14d 全链路无 rule:resolve 1101 (即时,L1=1001 咨询无 rule)→ matched=False

附加 14e:L4 沿父链命中 L2 — resolve 2322 → 2301,验证跨级 parent walk
"""
from __future__ import annotations

import pytest

from e2e_tests.tests import helpers
from e2e_tests.tests.helpers import ScenarioResult


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_parent_chain_l4_direct_hit(
    e2e_client, token, batch_id, result_collector
):
    """14a — L4 leaf 有 rule,resolve 直命中 L4 自身。"""
    # 2311 核心网系统 (L4) — 自带 rule
    r = helpers.resolve_routing(e2e_client, token, 2311)
    assert r.get("matched") is True, r
    assert r["matched_rule_category_id"] == 2311, (
        f"L4 命中应为 2311,实际={r.get('matched_rule_category_id')}"
    )
    assert r["dispatcher_name"] == "业务保障协调人", r

    result_collector.append(ScenarioResult(
        scenario="14a L4 直命中",
        category="2311 核心网系统 (L4)",
        state="matched-self",
        result="PASS",
        extra={"matched_rule_category_id": r["matched_rule_category_id"]},
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_parent_chain_l3_walks_to_l2(
    e2e_client, token, batch_id, result_collector
):
    """14b — L3 leaf 无 rule,resolve 沿父链(跳 L3→L2)命中 2301。"""
    # 2322 硬件故障 (L3,parent=2301 业务保障 L2) — 无 leaf rule,应上溯到 2301
    r = helpers.resolve_routing(e2e_client, token, 2322)
    assert r.get("matched") is True, r
    assert r["matched_rule_category_id"] == 2301, (
        f"2322 应匹配 2301,实际={r.get('matched_rule_category_id')}"
    )
    assert r["dispatcher_name"] == "业务保障协调人", r

    result_collector.append(ScenarioResult(
        scenario="14b L3 退回 L2 命中",
        category="2322 硬件故障 (L3)",
        state="matched-via-parent",
        result="PASS",
        extra={"matched_via": "2301", "matched_rule_category_id": r["matched_rule_category_id"]},
    ))


@pytest.mark.usefixtures("e2e_client", "token", "batch_id", "result_collector")
def test_parent_chain_l2_direct_hit(
    e2e_client, token, batch_id, result_collector
):
    """14c — L2 自身有 rule,resolve 直命中 L2。"""
    # 2301 业务保障 (L2) — 自带 rule
    r = helpers.resolve_routing(e2e_client, token, 2301)
    assert r.get("matched") is True, r
    assert r["matched_rule_category_id"] == 2301, r

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
    """14d — 全链路无 rule(1101 即时,L1=1001 咨询无 rule)→ matched=False。"""
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
    """14e — 投诉分级 L3 退回 L2:2103 (重要投诉) → 父链 2101 (服务投诉) 命中。

    验证投诉分级场景的 routing 继承路径与业务运营/保障场景一致。
    """
    r = helpers.resolve_routing(e2e_client, token, 2103)
    assert r.get("matched") is True, r
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