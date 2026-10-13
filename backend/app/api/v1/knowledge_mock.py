"""Admin-only mock of the ticket knowledge proxy, with no RAG connection."""

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import require_role

router = APIRouter(prefix="/knowledge", tags=["knowledge-prototype"], dependencies=[Depends(require_role("admin"))])

COLLECTIONS = [
    {"id": "demo-service", "name": "客服知识库", "description": "客服常见问题与处理说明", "document_count": 3},
    {"id": "demo-operations", "name": "业务保障资料", "description": "平台与终端处理参考", "document_count": 1},
]
DOCUMENTS = [
    {"id": "demo-pdf", "collection_id": "demo-service", "filename": "服务流程示例.pdf", "file_type": "pdf", "size_bytes": 2048, "status": "ready", "page_count": 1, "preview_available": True},
    {"id": "demo-text", "collection_id": "demo-service", "filename": "回访说明.txt", "file_type": "txt", "size_bytes": 88, "status": "ready", "page_count": None, "preview_available": True},
    {"id": "demo-image", "collection_id": "demo-service", "filename": "处理流程.svg", "file_type": "svg", "size_bytes": 410, "status": "ready", "page_count": None, "preview_available": True},
    {"id": "demo-docx", "collection_id": "demo-operations", "filename": "平台处理指南.docx", "file_type": "docx", "size_bytes": 1200, "status": "ready", "page_count": None, "preview_available": True},
]
CHUNKS = {
    "demo-pdf": {"chunk_id": "demo-pdf-page-1", "heading": "工单处理", "page": 1, "source_locator": {"kind": "pdf_page", "page": 1}, "text": "创建工单后，按问题分类流转至对应处理部门。"},
    "demo-text": {"chunk_id": "demo-text-section", "heading": "回访", "page": None, "source_locator": {"kind": "heading", "heading": "回访"}, "text": "处理完成后确认客户是否满意。"},
    "demo-image": {"chunk_id": "demo-image", "heading": "流程图", "page": None, "source_locator": {"kind": "heading", "heading": "流程图"}, "text": "创建、处理、回访。"},
    "demo-docx": {"chunk_id": "demo-docx-section", "heading": "平台处理", "page": None, "source_locator": {"kind": "heading", "heading": "平台处理"}, "text": "平台问题由运维组处理，售后负责致电反馈。"},
}


def _enabled() -> None:
    if not settings.KNOWLEDGE_MOCK_ENABLED:
        raise HTTPException(503, detail="知识库模拟接口未启用；真实 RAG 授权接口尚未接入")


def _collection(collection_id: str) -> dict:
    return next((row for row in COLLECTIONS if row["id"] == collection_id), None) or _not_found()


def _document(document_id: str) -> dict:
    return next((row for row in DOCUMENTS if row["id"] == document_id), None) or _not_found()


def _not_found():
    raise HTTPException(404, detail="资源不存在")


def _page(rows: list[dict], limit: int, cursor: str | None) -> dict:
    try:
        start = int(cursor or "0")
    except ValueError as exc:
        raise HTTPException(422, detail="无效的分页游标") from exc
    if start < 0:
        raise HTTPException(422, detail="无效的分页游标")
    end = start + limit
    return {"items": rows[start:end], "page_info": {"next_cursor": str(end) if end < len(rows) else None, "has_more": end < len(rows)}}


@router.get("/status")
async def status():
    _enabled()
    return {"mode": "mock"}


@router.get("/collections")
async def collections(limit: int = Query(20, ge=1, le=100), cursor: str | None = None):
    _enabled()
    return _page(COLLECTIONS, limit, cursor)


@router.get("/collections/{collection_id}/documents")
async def documents(collection_id: str, limit: int = Query(20, ge=1, le=100), cursor: str | None = None,
                    q: str = "", file_type: str = ""):
    _enabled()
    _collection(collection_id)
    rows = [row for row in DOCUMENTS if row["collection_id"] == collection_id
            and (not q or q.casefold() in row["filename"].casefold())
            and (not file_type or row["file_type"] == file_type)]
    return _page(rows, limit, cursor)


class QueryBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = "hybrid"


@router.post("/collections/{collection_id}/queries")
async def query_collection(collection_id: str, body: QueryBody):
    _enabled()
    _collection(collection_id)
    if body.mode not in ("hybrid", "keyword"):
        raise HTTPException(422, detail="无效的检索模式")
    terms = body.query.casefold()
    matches = [row for row in DOCUMENTS if row["collection_id"] == collection_id
               and (terms in row["filename"].casefold() or terms in CHUNKS[row["id"]]["text"].casefold())]
    return {"query_id": "demo-query", "answer": None, "citations": [
        {"document_id": row["id"], "document_name": row["filename"], **CHUNKS[row["id"]]}
        for row in matches[:body.top_k]
    ], "diagnostics": {"mock": True}}


@router.get("/documents/{document_id}")
async def document_detail(document_id: str):
    _enabled()
    return {**_document(document_id), "chunks": [CHUNKS[document_id]]}


@router.get("/documents/{document_id}/chunks/{chunk_id}")
async def chunk_detail(document_id: str, chunk_id: str):
    _enabled()
    _document(document_id)
    chunk = CHUNKS[document_id]
    if chunk_id != chunk["chunk_id"]:
        _not_found()
    return {"document_id": document_id, **chunk}


def _sample_pdf() -> bytes:
    commands = b"BT /F1 18 Tf 72 740 Td (Ticket knowledge preview) Tj ET"
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length " + str(len(commands)).encode() + b" >>\nstream\n" + commands + b"\nendstream",
    ]
    output = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, value in enumerate(objects, 1):
        offsets.append(len(output))
        output.extend(f"{index} 0 obj\n".encode() + value + b"\nendobj\n")
    start = len(output)
    output.extend(f"xref\n0 {len(offsets)}\n0000000000 65535 f \n".encode())
    for offset in offsets[1:]:
        output.extend(f"{offset:010d} 00000 n \n".encode())
    output.extend(f"trailer\n<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{start}\n%%EOF\n".encode())
    return bytes(output)


def _sample_docx() -> bytes:
    output = BytesIO()
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>')
        archive.writestr("_rels/.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>')
        archive.writestr("word/document.xml", '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>平台处理指南：售后致电反馈。</w:t></w:r></w:p></w:body></w:document>')
    return output.getvalue()


@router.get("/documents/{document_id}/file")
async def preview(document_id: str):
    _enabled()
    _document(document_id)
    content = {
        "demo-pdf": (_sample_pdf(), "application/pdf"),
        "demo-text": ("处理完成后，应由售后致电反馈，再由客服回访归档。\n".encode(), "text/plain; charset=utf-8"),
        "demo-image": (b'<svg xmlns="http://www.w3.org/2000/svg" width="720" height="300"><rect width="720" height="300" fill="#f1f3ff"/><text x="75" y="155" font-size="28" fill="#4341a9">Ticket knowledge preview</text></svg>', "image/svg+xml"),
        "demo-docx": (_sample_docx(), "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    }[document_id]
    return Response(content[0], media_type=content[1], headers={"Cache-Control": "no-store", "X-Knowledge-Mock": "true"})
