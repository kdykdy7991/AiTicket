"""Admin-only mock of the ticket knowledge proxy, with no RAG connection."""

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import require_role

router = APIRouter(prefix="/knowledge", tags=["knowledge-prototype"], dependencies=[Depends(require_role("admin", "observer"))])

COLLECTIONS = [
    {"id": "demo-service", "name": "客服知识库", "description": "客服常见问题与处理说明", "document_count": 3},
    {"id": "demo-operations", "name": "业务保障资料", "description": "平台与终端处理参考", "document_count": 4},
]
DOCUMENTS = [
    {"id": "demo-pdf", "collection_id": "demo-service", "filename": "服务流程示例.pdf", "file_type": "pdf", "size_bytes": 2048, "status": "ready", "page_count": 1},
    {"id": "demo-text", "collection_id": "demo-service", "filename": "回访说明.txt", "file_type": "txt", "size_bytes": 88, "status": "ready", "page_count": None},
    {"id": "demo-image", "collection_id": "demo-service", "filename": "处理流程.svg", "file_type": "svg", "size_bytes": 410, "status": "ready", "page_count": None},
    {"id": "demo-docx", "collection_id": "demo-operations", "filename": "平台处理指南.docx", "file_type": "docx", "size_bytes": 1200, "status": "ready", "page_count": None},
    {"id": "demo-manual", "collection_id": "demo-operations", "filename": "终端维护手册 V3.2.pdf", "file_type": "pdf", "size_bytes": 8192, "status": "ready", "page_count": 42},
    {"id": "demo-login", "collection_id": "demo-operations", "filename": "平台登录故障排查.pdf", "file_type": "pdf", "size_bytes": 4096, "status": "ready", "page_count": 12},
    {"id": "demo-apn", "collection_id": "demo-operations", "filename": "APN 配置说明.pdf", "file_type": "pdf", "size_bytes": 3072, "status": "ready", "page_count": 8},
    {"id": "demo-sim", "collection_id": "demo-operations", "filename": "SIM 激活异常案例.pdf", "file_type": "pdf", "size_bytes": 2048, "status": "ready", "page_count": 5},
]
CHUNKS = {
    "demo-pdf": {"chunk_id": "demo-pdf-page-1", "heading": "工单处理", "page": 1, "source_locator": {"kind": "pdf_page", "page": 1}, "text": "创建工单后，按问题分类流转至对应处理部门。"},
    "demo-text": {"chunk_id": "demo-text-section", "heading": "回访", "page": None, "source_locator": {"kind": "heading", "heading": "回访"}, "text": "处理完成后确认客户是否满意。"},
    "demo-image": {"chunk_id": "demo-image", "heading": "流程图", "page": None, "source_locator": {"kind": "heading", "heading": "流程图"}, "text": "创建、处理、回访。"},
    "demo-docx": {"chunk_id": "demo-docx-section", "heading": "平台处理", "page": None, "source_locator": {"kind": "heading", "heading": "平台处理"}, "text": "平台问题由运维组处理，售后负责致电反馈。"},
    "demo-manual": {"chunk_id": "demo-manual-chunk-1", "heading": "终端无法上线排查", "page": 42, "source_locator": {"kind": "pdf_page", "page": 42}, "text": "终端无法上线时，应优先检查 SIM 卡状态、APN 参数及网络注册状态。\n\n| 序号 | 用途 | 配置 |\n| --- | --- | --- |\n| 1 | 公共网络 | APN: cmnet |\n| 2 | 专网业务 | APN: private.vpn |\n\n确认以上参数后重启终端，再观察注册指示灯。"},
    "demo-login": {"chunk_id": "demo-login-chunk-1", "heading": "平台登录失败", "page": 3, "source_locator": {"kind": "pdf_page", "page": 3}, "text": "平台登录失败时先确认账号是否被锁定，再检查浏览器是否拦截了第三方 Cookie。"},
    "demo-apn": {"chunk_id": "demo-apn-chunk-1", "heading": "APN 配置", "page": 2, "source_locator": {"kind": "pdf_page", "page": 2}, "text": "APN 参数需与运营商发放的专网参数保持一致，错误配置会导致终端无法注册网络。"},
    "demo-sim": {"chunk_id": "demo-sim-chunk-1", "heading": "SIM 激活异常", "page": 1, "source_locator": {"kind": "pdf_page", "page": 1}, "text": "SIM 激活异常多为开通工单未回执，可在业务系统查询开通状态。"},
}
DEMO_NEIGHBORS = {
    "demo-pdf-before": {"text": "核实客户描述的现象，并确认终端供电与状态指示灯。", "index": 0,
                        "previous_chunk_id": None, "next_chunk_id": "demo-pdf-page-1"},
    "demo-pdf-page-1": {"text": CHUNKS["demo-pdf"]["text"], "index": 1,
                        "previous_chunk_id": "demo-pdf-before", "next_chunk_id": "demo-pdf-after"},
    "demo-pdf-after": {"text": "若终端侧检查正常，再确认平台侧设备注册状态。", "index": 2,
                       "previous_chunk_id": "demo-pdf-page-1", "next_chunk_id": None},
}


def _svg(title: str, rows: list[str]) -> bytes:
    body = "".join(f'<text x="24" y="{76 + index * 34}" font-family="sans-serif" font-size="16" fill="#1f2937">{row}</text>'
                   for index, row in enumerate(rows))
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="480" height="280" viewBox="0 0 480 280">'
            '<rect width="480" height="280" fill="#f8fafc"/>'
            f'<text x="24" y="44" font-family="sans-serif" font-size="18" font-weight="600" fill="#111827">{title}</text>'
            + body + '</svg>').encode("utf-8")


# 模拟 RAG Server 的 Document Presentation 与图片资产；工单侧只做展示，不生成内容
ASSETS = {
    "asset-apn-table": {"content_type": "image/svg+xml", "content": _svg("APN 参数对照", ["1  公共网络  cmnet", "2  专网业务  private.vpn"])},
    "asset-register-flow": {"content_type": "image/svg+xml", "content": _svg("终端注册流程", ["SIM 状态 → APN 参数 → 网络注册", "注册失败时回到 APN 校验"])},
}
PRESENTATIONS = {
    "demo-pdf": {
        "presentation_status": "ready",
        "summary": "说明工单从创建、分类流转到处理部门的基本流程。",
        "key_points": ["按问题分类流转至对应处理部门", "处理完成后进入回访确认"],
        "related_assets": [],
    },
    "demo-manual": {
        "presentation_status": "ready",
        "summary": "第 3 章给出终端无法上线时的排查顺序：SIM 卡状态、APN 参数、网络注册状态，并附常用 APN 参数对照表。",
        "key_points": [
            "优先检查 SIM 卡是否被停用或欠费",
            "APN 参数需与运营商发放的专网参数一致",
            "重启终端后观察网络注册指示灯状态",
        ],
        "related_assets": [
            {"asset_id": "asset-apn-table", "caption": "常用 APN 参数对照表", "source_chunk_id": "demo-manual-chunk-1", "content_type": "image"},
            {"asset_id": "asset-register-flow", "caption": "终端网络注册流程示意", "source_chunk_id": "demo-manual-chunk-1", "content_type": "image"},
        ],
    },
    "demo-login": {"presentation_status": "pending", "summary": "", "key_points": [], "related_assets": []},
    "demo-apn": {"presentation_status": "failed", "summary": "", "key_points": [], "related_assets": []},
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
               and any(terms in value.casefold() for value in (
                   row["filename"], CHUNKS[row["id"]]["text"], CHUNKS[row["id"]].get("heading") or ""))]
    return {"query_id": "demo-query", "answer": None,
            "citations": [_citation(row) for row in matches[:body.top_k]], "diagnostics": {"mock": True}}


def _citation(row: dict) -> dict:
    presentation = PRESENTATIONS.get(row["id"]) or {}
    assets = presentation.get("related_assets") or []
    summary = presentation.get("summary") or ""
    return {
        "document_id": row["id"], "document_name": row["filename"], **CHUNKS[row["id"]],
        "has_presentation": bool(presentation),
        "document_summary_preview": summary[:60] or None,
        "asset_ids": [item["asset_id"] for item in assets],
        "images": [{"asset_id": item["asset_id"], "caption": item.get("caption"),
                    "content_type": item.get("content_type")} for item in assets],
    }


@router.get("/documents/{document_id}")
async def document_detail(document_id: str):
    _enabled()
    return {**_document(document_id), "chunks": [CHUNKS[document_id]]}


@router.get("/documents/{document_id}/chunks")
async def chunks(document_id: str, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50)):
    _enabled()
    _document(document_id)
    chunk = CHUNKS[document_id]
    items = [{"chunk_id": chunk["chunk_id"], "index": 0, "heading": chunk["heading"],
              "page": chunk["page"], "content_type": "text", "character_count": len(chunk["text"]),
              "text_preview": chunk["text"]}] if page == 1 else []
    return {"items": items, "page": page, "page_size": page_size, "total": 1, "has_next": False}


@router.get("/documents/{document_id}/presentation")
async def document_presentation(document_id: str):
    _enabled()
    _document(document_id)
    return PRESENTATIONS.get(document_id) or _not_found()


@router.get("/assets/{asset_id}")
async def asset(asset_id: str):
    _enabled()
    item = ASSETS.get(asset_id) or _not_found()
    return Response(content=item["content"], media_type=item["content_type"],
                    headers={"Cache-Control": "private, max-age=300"})


@router.get("/documents/{document_id}/chunks/{chunk_id}")
async def chunk_detail(document_id: str, chunk_id: str):
    _enabled()
    _document(document_id)
    chunk = CHUNKS[document_id]
    if document_id == "demo-pdf" and chunk_id in DEMO_NEIGHBORS:
        neighbor = DEMO_NEIGHBORS[chunk_id]
        return {"document_id": document_id, "chunk_id": chunk_id, "index": neighbor["index"],
                "text": neighbor["text"], "heading": chunk["heading"], "page": chunk["page"],
                "source_locator": chunk["source_locator"], "content_type": "text",
                "character_count": len(neighbor["text"]), "previous_chunk_id": neighbor["previous_chunk_id"],
                "next_chunk_id": neighbor["next_chunk_id"]}
    if chunk_id != chunk["chunk_id"]:
        _not_found()
    return {"document_id": document_id, "index": 0, "content_type": "text",
            "character_count": len(chunk["text"]), "previous_chunk_id": None, "next_chunk_id": None, **chunk}
