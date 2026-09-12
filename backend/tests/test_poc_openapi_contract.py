"""OpenAPI 契约测试：Swagger 中不得出现旧业务角色、旧状态、旧优先级。"""

import json

from app.main import app

#: 旧客服流程枚举，任何新接口都不允许出现
LEGACY_TOKENS = [
    "agent",
    "handler",
    "dispatcher",
    "on_hold",
    "archived",
    "p1_urgent",
    "p2_high",
    "p3_normal",
    "p4_enterprise",
    "is_callbacked",
    "callback_required",
    "satisfaction",
]

#: 旧枚举值以 JSON 字符串形式出现时才算命中（避免误伤驼峰/子串）
LEGACY_QUOTED = ['"pending"', '"open"', '"on_hold"', '"archived"']

REQUIRED_TOKENS = [
    "presales",
    "approver",
    "taskforce",
    "subsystem",
    "quality",
    "admin",
    "pending_approval",
    "pending_routing",
    "planning",
    "pending_plan_confirmation",
    "processing",
    "pending_quality_review",
    "pending_final_approval",
    "closed",
    "returned",
    "cancelled",
    "p0_blocker",
    "p1_critical",
    "p2_normal",
    "p3_low",
    "resolved",
    "temporarily_resolved",
    "pending_reproduction",
    "unresolved",
    "approve",
    "reject",
    "route",
    "submit_plan",
    "confirm_plan",
    "submit_analysis",
    "pass_review",
    "approve_closure",
    "return",
    "resubmit",
    "cancel",
]


def _spec_text() -> str:
    return json.dumps(app.openapi(), ensure_ascii=False)


def test_openapi_contains_poc_enums():
    text = _spec_text()
    missing = [token for token in REQUIRED_TOKENS if token not in text]
    assert not missing, f"OpenAPI 缺少 POC 枚举：{missing}"


def test_openapi_has_no_legacy_enums():
    text = _spec_text().lower()
    hits = [token for token in LEGACY_TOKENS if token in text]
    assert not hits, f"OpenAPI 仍暴露旧业务枚举：{hits}"

    hits = [token for token in LEGACY_QUOTED if token in text]
    assert not hits, f"OpenAPI 仍暴露旧状态：{hits}"


def test_openapi_exposes_only_poc_endpoints():
    paths = set(app.openapi()["paths"])
    assert "/api/v1/tickets/{ticket_id}/actions" in paths
    assert "/api/v1/tickets/{ticket_id}/attachments" in paths
    assert "/api/v1/attachments/{attachment_id}/download" in paths

    for legacy in (
        "/api/v1/articles",
        "/api/v1/tickets/{ticket_id}/articles",
        "/api/v1/sla-policies",
        "/api/v1/categories",
        "/api/v1/regions",
        "/api/v1/groups",
        "/api/v1/tickets/batch-update",
    ):
        assert not [p for p in paths if p.startswith(legacy)], f"{legacy} 应已下线"
