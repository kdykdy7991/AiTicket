"""MCP transport smoke test without a running API or database."""

import httpx
import pytest

from mcp_server.app import app, mcp


@pytest.mark.asyncio
async def test_bearer_auth_and_tool_discovery(monkeypatch):
    monkeypatch.setenv("MCP_BEARER_TOKEN", "platform-secret")
    request = {"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
    headers = {
        "Accept": "application/json, text/event-stream",
        "Content-Type": "application/json",
        "MCP-Protocol-Version": "2025-11-25",
    }
    async with mcp.session_manager.run():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://localhost") as client:
            unauthenticated = await client.post("/mcp", json=request, headers=headers)
            assert unauthenticated.status_code == 401
            authorized = await client.post(
                "/mcp", json=request,
                headers={**headers, "Authorization": "Bearer platform-secret"},
            )
            with_copied_whitespace = await client.post(
                "/mcp", json=request,
                headers={**headers, "Authorization": "Bearer platform-secret  "},
            )
    assert authorized.status_code == 200, authorized.text
    assert with_copied_whitespace.status_code == 200, with_copied_whitespace.text
    names = {tool["name"] for tool in authorized.json()["result"]["tools"]}
    assert names == {"list_recent_tickets", "search_tickets", "get_ticket", "list_categories"}
