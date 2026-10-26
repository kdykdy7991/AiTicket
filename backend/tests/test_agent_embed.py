"""Trusted-app exchange uses the authenticated ticket user's identity."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import Response, Request

from app.core.config import settings
from app.core.deps import get_current_user
from app.main import app


@pytest.mark.asyncio
async def test_admin_exchanges_only_own_identity(client, monkeypatch):
    http, _, _ = client
    monkeypatch.setattr(settings, "AGENT_EMBED_URL", "http://127.0.0.1:5176/embed/pub_01a11f5f-b98e-76ef-8f79-afd6a828a538")
    monkeypatch.setattr(settings, "AGENT_EMBED_API_URL", "http://debussy.internal:8765")
    monkeypatch.setattr(settings, "AGENT_EMBED_CLIENT_ID", "ta_test")
    monkeypatch.setattr(settings, "AGENT_EMBED_CLIENT_SECRET", "server-only-secret")
    code = "a" * 43
    fake_response = Response(200, json={"data": {"code": code, "expiresIn": 60}}, request=Request("POST", "http://debussy.internal:8765/api/embed/v1/auth/exchange"))

    missing_origin = await http.post("/api/v1/agent/embed/code")
    assert missing_origin.status_code == 400

    app.dependency_overrides[get_current_user] = lambda: type("Admin", (), {"id": 1, "name": "管理员", "role": "admin"})()
    upstream = MagicMock()
    upstream.__aenter__ = AsyncMock(return_value=upstream)
    upstream.__aexit__ = AsyncMock(return_value=None)
    upstream.post = AsyncMock(return_value=fake_response)
    with patch("app.api.v1.agent_embed.httpx.AsyncClient", return_value=upstream):
        response = await http.post("/api/v1/agent/embed/code", headers={"Origin": "http://localhost:5173"})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["data"] == {
        "embed_url": settings.AGENT_EMBED_URL,
        "code": code,
        "expires_in": 60,
    }
    kwargs = upstream.post.await_args.kwargs
    assert kwargs["json"] == {
        "publicAppId": "pub_01a11f5f-b98e-76ef-8f79-afd6a828a538",
        "origin": "http://localhost:5173",
        "userId": "1",
        "name": "管理员",
        "roles": ["admin"],
    }
    assert kwargs["headers"]["Authorization"] == "Bearer ta_test.server-only-secret"
    assert "server-only-secret" not in str(response.json())

    platform_denial = Response(403, json={"error": "origin_not_allowed"},
                               request=Request("POST", "http://debussy.internal:8765/api/embed/v1/auth/exchange"))
    upstream.post = AsyncMock(return_value=platform_denial)
    with patch("app.api.v1.agent_embed.httpx.AsyncClient", return_value=upstream):
        denied = await http.post("/api/v1/agent/embed/code", headers={"Origin": "http://evil.example"})
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Agent 平台未允许当前页面来源"
    assert upstream.post.await_args.kwargs["json"]["origin"] == "http://evil.example"

    app.dependency_overrides[get_current_user] = lambda: type("Agent", (), {"id": 9, "role": "agent"})()
    forbidden = await http.post("/api/v1/agent/embed/code", headers={"Origin": "http://localhost:5173"})
    assert forbidden.status_code == 403
