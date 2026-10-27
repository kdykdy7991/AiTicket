"""Authenticated, read-only proxy for the RAG project's knowledge API."""

import logging
from pathlib import PurePath
from urllib.parse import quote

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from app.core.config import settings
from app.core.deps import require_role
from app.models.user import User

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)

# 知识派生资产只转发图片，避免把任意上游文件透传到浏览器
MAX_ASSET_BYTES = 8 * 1024 * 1024


def _url(path: str) -> str:
    if not settings.RAG_API_URL or not settings.RAG_SERVICE_TOKEN:
        raise HTTPException(503, detail="知识库服务尚未配置")
    return f"{settings.RAG_API_URL.rstrip('/')}/api/v1{path}"


def _headers(user: User) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {settings.RAG_SERVICE_TOKEN}",
        "X-Audit-User-ID": f"ticket:{user.id}",
    }


def _id(value: str) -> str:
    return quote(value, safe="")


def _upstream_error(response: httpx.Response) -> HTTPException:
    request_id = response.headers.get("x-request-id", "")
    try:
        error = response.json().get("error", {})
        request_id = error.get("request_id") or request_id
        code = error.get("code", "")
    except (ValueError, AttributeError):
        code = ""
    logger.warning("RAG knowledge request failed: status=%s code=%s request_id=%s", response.status_code, code, request_id)
    if response.status_code == 404:
        return HTTPException(404, detail="知识库资源不存在或无权访问")
    if response.status_code == 401:
        return HTTPException(502, detail="知识库服务认证失败")
    return HTTPException(502, detail="知识库服务暂不可用")


async def _request(method: str, path: str, user: User, *, params: dict | None = None, body: dict | None = None) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.request(method, _url(path), headers=_headers(user),
                                            params={key: value for key, value in (params or {}).items() if value is not None},
                                            json=body)
    except httpx.HTTPError as exc:
        logger.warning("RAG knowledge transport failed: %s", type(exc).__name__)
        raise HTTPException(502, detail="无法连接知识库服务") from exc
    if response.is_error:
        raise _upstream_error(response)
    return response


async def _json(method: str, path: str, user: User, *, params: dict | None = None, body: dict | None = None) -> dict:
    response = await _request(method, path, user, params=params, body=body)
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(502, detail="知识库服务响应无效") from exc


def _document(row: dict) -> dict:
    filename = row.get("filename", "")
    file_type = PurePath(filename).suffix.lstrip(".").lower()
    return {**row, "file_type": file_type}


@router.get("/status")
async def status(user: User = Depends(require_role("admin", "observer"))):
    _url("/collections")
    return {"mode": "rag"}


@router.get("/collections")
async def collections(limit: int = Query(20, ge=1, le=100), cursor: str | None = None,
                      user: User = Depends(require_role("admin", "observer"))):
    return await _json("GET", "/collections", user, params={"limit": limit, "cursor": cursor})


@router.get("/collections/{collection_id}/documents")
async def documents(collection_id: str, limit: int = Query(20, ge=1, le=100), cursor: str | None = None,
                    q: str = "", file_type: str = "", user: User = Depends(require_role("admin", "observer"))):
    result = await _json("GET", f"/collections/{_id(collection_id)}/documents", user,
                         params={"limit": limit, "cursor": cursor, "q": q or None, "file_type": file_type or None})
    return {**result, "items": [_document(row) for row in result.get("items", [])]}


class QueryBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = "hybrid"


@router.post("/collections/{collection_id}/queries")
async def query_collection(collection_id: str, body: QueryBody, user: User = Depends(require_role("admin", "observer"))):
    return await _json("POST", f"/collections/{_id(collection_id)}/queries", user, body=body.model_dump())


@router.get("/documents/{document_id}")
async def document_detail(document_id: str, user: User = Depends(require_role("admin", "observer"))):
    return _document(await _json("GET", f"/documents/{_id(document_id)}", user))


@router.get("/documents/{document_id}/chunks")
async def chunks(document_id: str, page: int = Query(1, ge=1), page_size: int = Query(10, ge=1, le=50),
                 user: User = Depends(require_role("admin", "observer"))):
    return await _json("GET", f"/documents/{_id(document_id)}/chunks", user,
                       params={"page": page, "page_size": page_size})


@router.get("/documents/{document_id}/chunks/{chunk_id}")
async def chunk_detail(document_id: str, chunk_id: str, user: User = Depends(require_role("admin", "observer"))):
    return await _json("GET", f"/documents/{_id(document_id)}/chunks/{_id(chunk_id)}", user)


@router.get("/documents/{document_id}/presentation")
async def document_presentation(document_id: str, user: User = Depends(require_role("admin", "observer"))):
    """Document Presentation：只读转发摘要、重点和派生图片资产引用。"""
    return await _json("GET", f"/documents/{_id(document_id)}/presentation", user)


@router.get("/assets/{asset_id}")
async def asset(asset_id: str, user: User = Depends(require_role("admin", "observer"))):
    """只返回图片类知识派生资产；不代理原文件。"""
    response = await _request("GET", f"/assets/{_id(asset_id)}", user)
    content_type = response.headers.get("content-type", "").split(";")[0].strip().lower()
    if not content_type.startswith("image/"):
        logger.warning("RAG asset rejected: asset_id=%s content_type=%s", asset_id, content_type)
        raise HTTPException(415, detail="不支持的知识资产类型")
    if len(response.content) > MAX_ASSET_BYTES:
        raise HTTPException(413, detail="知识资产过大")
    return Response(content=response.content, media_type=content_type,
                    headers={"Cache-Control": "private, max-age=300",
                             "Content-Disposition": "inline",
                             "X-Content-Type-Options": "nosniff"})
