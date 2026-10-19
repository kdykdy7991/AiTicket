"""User management keeps agent and handler department assignments explicit."""

import pytest


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
