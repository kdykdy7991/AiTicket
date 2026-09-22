"""E2E 共享工具:登录、查实体、断言、报告生成。

设计原则:
- 不直接写数据库,所有断言都走真实 API
- 通过业务属性(username / name)查找实体,避免硬编码 id
- 每个工单的 customer_name 与 description 都带 E2E 前缀与 batch_id,
  方便 cleanup 与人工定位
"""
from __future__ import annotations

import json
import os
import time
import uuid
from datetime import datetime, timezone
from typing import Any

import httpx

API_BASE = os.environ.get("SKDY_API_BASE", "http://127.0.0.1:8001")
ADMIN_USERNAME = os.environ.get("SKDY_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("SKDY_ADMIN_PASS", "admin123")

E2E_CUSTOMER_PREFIX = "E2E-"
E2E_DESC_PREFIX = "[E2E]"
DEMO_CUSTOMER_PREFIX = "DEMO-"
DEMO_DESC_PREFIX = "[DEMO]"


def new_batch_id() -> str:
    """生成 batch_id。"""
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def admin_token(client: httpx.Client) -> str:
    """登录 admin 拿 token。每次都重新登录以避开 token_version 单旋。"""
    r = client.post(
        f"{API_BASE}/api/v1/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
    )
    r.raise_for_status()
    return r.json()["access_token"]


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# ── 创建工单的 payload 构造 ─────────────────────────────────────
def base_ticket_payload(
    *,
    customer_name: str,
    description: str,
    priority: str = "p3_normal",
    category_id: int | None = None,
    dispatcher_id: int | None = None,
    owner_id: int | None = None,
    handler_skill_group_id: int | None = None,
    complaint_level: str | None = None,
    root_cause: str | None = None,
    solution: str | None = None,
    resolution: str | None = None,
    is_instant_resolve: bool = False,
    instant_resolution: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "description": description,
        "priority": priority,
        "channel": "phone",
        "customer_type": "personal",
        "customer_name": customer_name,
        "customer_phone": "1390000" + uuid.uuid4().hex[:4].upper(),
    }
    if category_id is not None:
        payload["category_id"] = category_id
    if dispatcher_id is not None:
        payload["dispatcher_id"] = dispatcher_id
    if owner_id is not None:
        payload["owner_id"] = owner_id
    if handler_skill_group_id is not None:
        payload["handler_skill_group_id"] = handler_skill_group_id
    if complaint_level is not None:
        payload["complaint_level"] = complaint_level
    if root_cause is not None:
        payload["root_cause"] = root_cause
    if solution is not None:
        payload["solution"] = solution
    if resolution is not None:
        # resolution 通常由 PATCH /tickets 走状态机写入,不在 create payload 里
        payload["resolution"] = resolution
    if is_instant_resolve:
        payload["is_instant_resolve"] = True
    if instant_resolution is not None:
        payload["instant_resolution"] = instant_resolution
    if extra:
        payload.update(extra)
    return payload


def create_ticket(
    client: httpx.Client,
    token: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    r = client.post(
        f"{API_BASE}/api/v1/tickets",
        json=payload,
        headers=auth_headers(token),
    )
    r.raise_for_status()
    body = r.json()
    return body["data"] if "data" in body else body


def get_ticket(client: httpx.Client, token: str, ticket_id: int) -> dict[str, Any]:
    r = client.get(
        f"{API_BASE}/api/v1/tickets/{ticket_id}",
        headers=auth_headers(token),
    )
    r.raise_for_status()
    return r.json()


def get_state_logs(
    client: httpx.Client, token: str, ticket_id: int
) -> list[dict[str, Any]]:
    r = client.get(
        f"{API_BASE}/api/v1/tickets/{ticket_id}/state-logs",
        headers=auth_headers(token),
    )
    r.raise_for_status()
    body = r.json()
    return body.get("data", []) if isinstance(body, dict) else body


def get_state_logs_until(
    client: httpx.Client,
    token: str,
    ticket_id: int,
    *,
    predicate,
    max_attempts: int = 5,
    interval: float = 0.1,
) -> list[dict[str, Any]]:
    """轮询 state-logs 直到 predicate(logs) 为 True。

    解决 PATCH 提交后下一发 GET 偶发看不到刚写入的 state_log 行
    (异步连接池在同一 transaction 复用导致)。
    """
    last: list[dict[str, Any]] = []
    for _ in range(max_attempts):
        last = get_state_logs(client, token, ticket_id)
        if predicate(last):
            return last
        time.sleep(interval)
    return last


def get_ticket_until_state(
    client: httpx.Client,
    token: str,
    ticket_id: int,
    *,
    target_state: str,
    max_attempts: int = 5,
    interval: float = 0.1,
) -> dict[str, Any]:
    """轮询 ticket 详情直到 state == target_state。

    解决 PATCH 后立刻 GET 偶发拿到的还是旧 state 的抢跑。
    """
    last = get_ticket(client, token, ticket_id)
    for _ in range(max_attempts):
        if last.get("state") == target_state:
            return last
        time.sleep(interval)
        last = get_ticket(client, token, ticket_id)
    return last


def patch_ticket(
    client: httpx.Client,
    token: str,
    ticket_id: int,
    payload: dict[str, Any],
) -> dict[str, Any]:
    r = client.patch(
        f"{API_BASE}/api/v1/tickets/{ticket_id}",
        json=payload,
        headers=auth_headers(token),
    )
    r.raise_for_status()
    return r.json()


def list_tickets_by_customer(
    client: httpx.Client,
    token: str,
    customer_prefix: str,
    page_size: int = 100,
) -> list[dict[str, Any]]:
    """用 keyword(ilike) 查 customer_name 前缀的所有工单。"""
    r = client.get(
        f"{API_BASE}/api/v1/tickets",
        params={"keyword": customer_prefix, "page_size": page_size},
        headers=auth_headers(token),
    )
    r.raise_for_status()
    body = r.json()
    return body.get("data", []) if isinstance(body, dict) else body


def resolve_routing(
    client: httpx.Client, token: str, category_id: int
) -> dict[str, Any]:
    """POST /routing-rules/resolve → {data:{matched, ...}} 或未匹配。"""
    r = client.post(
        f"{API_BASE}/api/v1/routing-rules/resolve",
        json={"category_id": category_id},
        headers=auth_headers(token),
    )
    r.raise_for_status()
    body = r.json()
    return body.get("data", {}) if isinstance(body, dict) else body


def list_categories(client: httpx.Client, token: str) -> list[dict[str, Any]]:
    r = client.get(
        f"{API_BASE}/api/v1/categories?include_inactive=true",
        headers=auth_headers(token),
    )
    r.raise_for_status()
    body = r.json()
    tree = body.get("data", []) if isinstance(body, dict) else body
    # 后端返回 L1 树形 + 嵌套 children;E2E 用 flatten 一次性查找 leaf
    flat: list[dict[str, Any]] = []

    def _walk(nodes: list[dict[str, Any]]) -> None:
        for n in nodes:
            flat.append(n)
            _walk(n.get("children") or [])

    _walk(tree)
    return flat


def list_users(client: httpx.Client, token: str, page_size: int = 200) -> list[dict[str, Any]]:
    r = client.get(
        f"{API_BASE}/api/v1/users?page_size={page_size}",
        headers=auth_headers(token),
    )
    r.raise_for_status()
    body = r.json()
    return body.get("data", []) if isinstance(body, dict) else body


def list_skill_groups(
    client: httpx.Client, token: str, page_size: int = 200
) -> list[dict[str, Any]]:
    r = client.get(
        f"{API_BASE}/api/v1/skill-groups?page_size={page_size}",
        headers=auth_headers(token),
    )
    r.raise_for_status()
    body = r.json()
    return body.get("data", []) if isinstance(body, dict) else body


# ── 业务查找(按业务属性查 id,不写死数字) ─────────────────────────
def find_user_by_name(
    client: httpx.Client, token: str, name: str
) -> dict[str, Any] | None:
    users = list_users(client, token)
    for u in users:
        if u.get("name") == name and u.get("is_active"):
            return u
    return None


def find_skill_group_by_name(
    client: httpx.Client, token: str, name: str
) -> dict[str, Any] | None:
    sgs = list_skill_groups(client, token)
    for sg in sgs:
        if sg.get("name") == name:
            return sg
    return None


def find_category_by_name(
    client: httpx.Client, token: str, name: str
) -> dict[str, Any] | None:
    cats = list_categories(client, token)
    for c in cats:
        if c.get("name") == name:
            return c
    return None


def find_dispatcher_user(
    client: httpx.Client, token: str, skill_group_id: int, name: str | None = None
) -> dict[str, Any] | None:
    """在指定 skill_group 下找 is_dispatcher=true 的用户;可选 name 限定。"""
    r = client.get(
        f"{API_BASE}/api/v1/skill-groups/{skill_group_id}/dispatchers",
        headers=auth_headers(token),
    )
    r.raise_for_status()
    body = r.json()
    users = body.get("data", []) if isinstance(body, dict) else body
    if name:
        for u in users:
            if u.get("name") == name:
                return u
        return None
    return users[0] if users else None


def find_handler_user(
    client: httpx.Client, token: str, skill_group_id: int, name: str | None = None
) -> dict[str, Any] | None:
    r = client.get(
        f"{API_BASE}/api/v1/skill-groups/{skill_group_id}/handlers",
        headers=auth_headers(token),
    )
    r.raise_for_status()
    body = r.json()
    users = body.get("data", []) if isinstance(body, dict) else body
    if name:
        for u in users:
            if u.get("name") == name:
                return u
        return None
    return users[0] if users else None


# ── 结果收集 ─────────────────────────────────────────────────────
class ScenarioResult:
    __slots__ = (
        "scenario", "ticket_number", "ticket_id", "category",
        "state", "dispatcher", "owner", "result", "extra",
    )

    def __init__(
        self,
        scenario: str,
        *,
        ticket_number: str | None = None,
        ticket_id: int | None = None,
        category: str | None = None,
        state: str | None = None,
        dispatcher: str | None = None,
        owner: str | None = None,
        result: str = "PASS",
        extra: dict[str, Any] | None = None,
    ):
        self.scenario = scenario
        self.ticket_number = ticket_number
        self.ticket_id = ticket_id
        self.category = category
        self.state = state
        self.dispatcher = dispatcher
        self.owner = owner
        self.result = result
        self.extra = extra or {}


def scenario_marker(category_name: str) -> str:
    """给工单标 E2E- 前缀(描述里带 batch_id)。"""
    return f"{E2E_CUSTOMER_PREFIX}{category_name}"


def describe_ticket(scenario_label: str, batch_id: str) -> str:
    return f"{E2E_DESC_PREFIX}[{batch_id}] {scenario_label}"