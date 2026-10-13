"""The RAG proxy keeps project credentials server-side and preserves byte ranges."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.api.v1 import knowledge
from app.core.config import settings
from app.core.security import decode_token


@pytest.mark.asyncio
async def test_rag_proxy_auth_audit_and_range(monkeypatch):
    monkeypatch.setattr(settings, "RAG_API_URL", "http://rag.test")
    monkeypatch.setattr(settings, "RAG_SERVICE_TOKEN", "private-test-token")
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer private-test-token"
        assert request.headers["x-audit-user-id"] == "ticket:7"
        if request.url.path.endswith("/preview"):
            assert request.headers["range"] == "bytes=0-3"
            return httpx.Response(206, stream=httpx.ByteStream(b"%PDF"), headers={"Content-Type": "application/pdf", "Content-Range": "bytes 0-3/100", "Accept-Ranges": "bytes"})
        return httpx.Response(200, json={"items": [{"id": "collection-id", "name": "skdy-common"}], "page_info": {"has_more": False, "next_cursor": None}})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(knowledge.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    user = SimpleNamespace(id=7)
    result = await knowledge._json("GET", "/collections", user)
    assert result["items"][0]["name"] == "skdy-common"

    request = Request({"type": "http", "method": "GET", "path": "/", "headers": [(b"range", b"bytes=0-3")]})
    response = await knowledge.preview("document-id", request, user)
    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-3/100"
    assert b"".join([part async for part in response.body_iterator]) == b"%PDF"
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_rag_service_unauthorized_is_not_local_login_failure(monkeypatch):
    monkeypatch.setattr(settings, "RAG_API_URL", "http://rag.test")
    monkeypatch.setattr(settings, "RAG_SERVICE_TOKEN", "wrong")
    original_client = httpx.AsyncClient
    monkeypatch.setattr(knowledge.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {"code": "PROJECT_UNAUTHORIZED"}})), **kwargs))
    with pytest.raises(HTTPException) as exc:
        await knowledge._json("GET", "/collections", SimpleNamespace(id=7))
    assert exc.value.status_code == 502


@pytest.mark.asyncio
async def test_pdf_preview_session_is_document_bound(monkeypatch):
    async def authorized_document(*args, **kwargs):
        return {"id": "doc-1"}

    monkeypatch.setattr(knowledge, "_json", authorized_document)
    monkeypatch.setattr(settings, "RAG_API_URL", "http://rag.test")
    monkeypatch.setattr(settings, "RAG_SERVICE_TOKEN", "private-test-token")
    original_client = httpx.AsyncClient
    monkeypatch.setattr(knowledge.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(lambda request: httpx.Response(206, stream=httpx.ByteStream(b"%"))), **kwargs))
    user = SimpleNamespace(id=7, token_version=3)
    request = Request({"type": "http", "scheme": "http", "method": "POST", "path": "/", "headers": []})
    response = await knowledge.create_preview_session("doc-1", request, user)
    cookie = response.headers["set-cookie"]
    assert "HttpOnly" in cookie
    assert "SameSite=lax" in cookie
    assert "Path=/api/v1/knowledge/documents/doc-1/file" in cookie
    token = cookie.split("kb_preview=", 1)[1].split(";", 1)[0]
    payload = decode_token(token)
    assert payload["doc"] == "doc-1"
    assert payload["sub"] == "7"
