"""Knowledge prototype remains isolated from RAG data and normal users."""

from app.core.config import settings
from test_workflow_regression import as_user


async def test_knowledge_mock_is_disabled_without_explicit_setting(client, monkeypatch):
    http, _, _ = client
    monkeypatch.setattr(settings, "KNOWLEDGE_MOCK_ENABLED", False)
    response = await http.get("/api/v1/knowledge/collections")
    assert response.status_code == 503


async def test_knowledge_mock_browse_search_and_preview(client, monkeypatch):
    http, _, _ = client
    monkeypatch.setattr(settings, "KNOWLEDGE_MOCK_ENABLED", True)

    collections = await http.get("/api/v1/knowledge/collections")
    assert collections.status_code == 200
    assert collections.json()["items"][0]["id"] == "demo-service"
    docs = await http.get("/api/v1/knowledge/collections/demo-service/documents", params={"file_type": "pdf"})
    assert [doc["id"] for doc in docs.json()["items"]] == ["demo-pdf"]
    search = await http.post("/api/v1/knowledge/collections/demo-service/queries", json={"query": "工单"})
    citation = search.json()["citations"][0]
    assert citation["document_id"] == "demo-pdf"
    assert citation["source_locator"] == {"kind": "pdf_page", "page": 1}
    detail = await http.get("/api/v1/knowledge/documents/demo-pdf")
    assert detail.json()["preview_available"] is True
    source = await http.get("/api/v1/knowledge/documents/demo-pdf/chunks/demo-pdf-page-1")
    assert source.json()["page"] == 1
    pdf = await http.get("/api/v1/knowledge/documents/demo-pdf/file")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert pdf.content.startswith(b"%PDF-1.4")
    assert (await http.get("/api/v1/knowledge/documents/missing")).status_code == 404

    with as_user(999, "agent"):
        forbidden = await http.get("/api/v1/knowledge/collections")
    assert forbidden.status_code == 403
