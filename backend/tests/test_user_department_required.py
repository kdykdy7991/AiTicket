"""User management keeps agent and handler department assignments explicit."""

import pytest

from app.core.config import settings


@pytest.mark.asyncio
async def test_user_management_requires_a_group(client):
    http, _, _ = client
    handler = await http.post("/api/v1/users", json={
        "username": "unaffiliated-handler", "name": "未分组处理人",
        "password": "password123", "role": "handler", "skill_groups": [],
    })
    assert handler.status_code == 422

    agent = await http.post("/api/v1/users", json={
        "username": "unaffiliated-agent", "name": "未分组客服",
        "password": "password123", "role": "agent",
    })
    assert agent.status_code == 422


@pytest.mark.asyncio
async def test_created_handler_can_log_in_with_password_when_casdoor_is_configured(client, monkeypatch):
    http, _, _ = client
    monkeypatch.setattr(settings, "CASDOOR_ISSUER", "http://casdoor.test")
    monkeypatch.setattr(settings, "CASDOOR_CLIENT_ID", "ticket-client")
    monkeypatch.setattr(settings, "CASDOOR_CLIENT_SECRET", "server-secret")
    monkeypatch.setattr(settings, "CASDOOR_REDIRECT_ORIGINS", "http://localhost:5173")
    group = await http.post("/api/v1/skill-groups", json={"name": "新建处理人登录测试组"})
    assert group.status_code == 201, group.text
    group_id = group.json()["data"]["id"]
    created = await http.post("/api/v1/users", json={
        "username": "new-handler-login", "name": "新建处理人", "password": "password123",
        "role": "handler", "skill_groups": [{"skill_group_id": group_id, "is_dispatcher": True}],
    })
    assert created.status_code == 201, created.text
    logged_in = await http.post("/api/v1/auth/login", json={
        "username": "new-handler-login", "password": "password123",
    })
    assert logged_in.status_code == 200, logged_in.text
    assert logged_in.json()["user"]["name"] == "新建处理人"
