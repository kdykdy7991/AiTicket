"""Knowledge prototype remains isolated from RAG data and normal users."""

from app.core.config import settings
from test_workflow_regression import as_user


async def test_knowledge_mock_is_disabled_without_explicit_setting(client, monkeypatch):
    http, _, _ = client
    monkeypatch.setattr(settings, "KNOWLEDGE_MOCK_ENABLED", False)
    response = await http.get("/api/v1/knowledge/collections")
    assert response.status_code == 503


async def test_knowledge_mock_browse_search_and_chunks(client, monkeypatch):
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
    assert detail.json()["filename"] == "服务流程示例.pdf"
    listing = await http.get("/api/v1/knowledge/documents/demo-pdf/chunks")
    assert listing.json()["items"][0]["chunk_id"] == citation["chunk_id"]
    source = await http.get("/api/v1/knowledge/documents/demo-pdf/chunks/demo-pdf-page-1")
    assert source.json()["page"] == 1
    assert source.json()["text"] == "创建工单后，按问题分类流转至对应处理部门。"
    previous = await http.get(f"/api/v1/knowledge/documents/demo-pdf/chunks/{source.json()['previous_chunk_id']}")
    assert "状态指示灯" in previous.json()["text"]
    assert (await http.get("/api/v1/knowledge/documents/demo-pdf/file")).status_code == 404
    assert (await http.post("/api/v1/knowledge/documents/demo-pdf/preview-session")).status_code == 404
    assert (await http.get("/api/v1/knowledge/documents/missing")).status_code == 404


    with as_user(999, "agent"):
        forbidden = await http.get("/api/v1/knowledge/collections")
    assert forbidden.status_code == 403


async def test_knowledge_mock_presentation_and_image_assets(client, monkeypatch):
    """Document Presentation 与图片资产只读可消费；原文件接口不存在。"""
    http, _, _ = client
    monkeypatch.setattr(settings, "KNOWLEDGE_MOCK_ENABLED", True)

    ready = await http.get("/api/v1/knowledge/documents/demo-manual/presentation")
    assert ready.status_code == 200
    assert ready.json()["presentation_status"] == "ready"
    assert ready.json()["key_points"][0]
    asset_id = ready.json()["related_assets"][0]["asset_id"]

    pending = await http.get("/api/v1/knowledge/documents/demo-login/presentation")
    assert pending.json()["presentation_status"] == "pending"
    assert (await http.get("/api/v1/knowledge/documents/demo-apn/presentation")).json()["presentation_status"] == "failed"
    # 没有 presentation 的文档按 404 处理，页面隐藏摘要区
    assert (await http.get("/api/v1/knowledge/documents/demo-sim/presentation")).status_code == 404

    asset = await http.get(f"/api/v1/knowledge/assets/{asset_id}")
    assert asset.status_code == 200
    assert asset.headers["content-type"].startswith("image/")
    assert (await http.get("/api/v1/knowledge/assets/missing")).status_code == 404
    assert (await http.get("/api/v1/knowledge/documents/demo-manual/file")).status_code == 404
    assert (await http.get("/api/v1/knowledge/documents/demo-manual/download")).status_code == 404

    with as_user(999, "agent"):
        forbidden = await http.get("/api/v1/knowledge/assets/" + asset_id)
    assert forbidden.status_code == 403
