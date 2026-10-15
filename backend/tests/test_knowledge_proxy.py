"""The RAG proxy keeps project credentials server-side for chunk reads."""

from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException

from app.api.v1 import knowledge
from app.core.config import settings


@pytest.mark.asyncio
async def test_rag_proxy_auth_audit_and_chunks(monkeypatch):
    monkeypatch.setattr(settings, "RAG_API_URL", "http://rag.test")
    monkeypatch.setattr(settings, "RAG_SERVICE_TOKEN", "private-test-token")
    seen = []

    def handler(request: httpx.Request):
        seen.append(request)
        assert request.headers["authorization"] == "Bearer private-test-token"
        assert request.headers["x-audit-user-id"] == "ticket:7"
        if request.url.path.endswith("/chunks"):
            assert request.url.params["page"] == "2"
            return httpx.Response(200, json={"items": [{"chunk_id": "chunk-11", "index": 10}], "page": 2, "page_size": 10, "total": 11, "has_next": False})
        return httpx.Response(200, json={"chunk_id": "chunk-11", "index": 10, "text": "处理步骤"})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(knowledge.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    user = SimpleNamespace(id=7)
    listing = await knowledge.chunks("document-id", page=2, page_size=10, user=user)
    assert listing["items"][0]["index"] == 10
    detail = await knowledge.chunk_detail("document-id", "chunk-11", user)
    assert detail["text"] == "处理步骤"
    assert len(seen) == 2


@pytest.mark.asyncio
async def test_rag_proxy_presentation_and_image_asset(monkeypatch):
    monkeypatch.setattr(settings, "RAG_API_URL", "http://rag.test")
    monkeypatch.setattr(settings, "RAG_SERVICE_TOKEN", "private-test-token")

    def handler(request: httpx.Request):
        if request.url.path.endswith("/presentation"):
            return httpx.Response(200, json={"presentation_status": "ready", "summary": "文档摘要",
                                             "key_points": ["重点一"], "related_assets": [
                                                 {"asset_id": "asset-1", "caption": "示意图", "content_type": "image"}]})
        if "/assets/" in request.url.path:
            return httpx.Response(200, content=b"\x89PNG", headers={"content-type": "image/png"})
        return httpx.Response(200, json={})

    original_client = httpx.AsyncClient
    monkeypatch.setattr(knowledge.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(handler), **kwargs))
    user = SimpleNamespace(id=7)
    presentation = await knowledge.document_presentation("document-id", user=user)
    assert presentation["summary"] == "文档摘要"
    assert presentation["related_assets"][0]["asset_id"] == "asset-1"
    asset = await knowledge.asset("asset-1", user=user)
    assert asset.media_type == "image/png"
    assert asset.body == b"\x89PNG"


@pytest.mark.asyncio
async def test_rag_proxy_rejects_non_image_asset(monkeypatch):
    monkeypatch.setattr(settings, "RAG_API_URL", "http://rag.test")
    monkeypatch.setattr(settings, "RAG_SERVICE_TOKEN", "private-test-token")
    original_client = httpx.AsyncClient
    monkeypatch.setattr(knowledge.httpx, "AsyncClient", lambda **kwargs: original_client(
        transport=httpx.MockTransport(lambda request: httpx.Response(200, content=b"%PDF", headers={"content-type": "application/pdf"})), **kwargs))
    with pytest.raises(HTTPException) as exc:
        await knowledge.asset("asset-1", user=SimpleNamespace(id=7))
    assert exc.value.status_code == 415


@pytest.mark.asyncio
async def test_rag_service_unauthorized_is_not_local_login_failure(monkeypatch):
    monkeypatch.setattr(settings, "RAG_API_URL", "http://rag.test")
    monkeypatch.setattr(settings, "RAG_SERVICE_TOKEN", "wrong")
    original_client = httpx.AsyncClient
    monkeypatch.setattr(knowledge.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {"code": "PROJECT_UNAUTHORIZED"}})), **kwargs))
    with pytest.raises(HTTPException) as exc:
        await knowledge._json("GET", "/collections", SimpleNamespace(id=7))
    assert exc.value.status_code == 502
