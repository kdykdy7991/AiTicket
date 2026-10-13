"""Authenticated, read-only proxy for the RAG project's knowledge API."""

import logging
from datetime import datetime, timedelta, timezone
from pathlib import PurePath
from urllib.parse import quote

import httpx
from jose import jwt
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user, require_role
from app.core.security import decode_token
from app.models.user import User

router = APIRouter(prefix="/knowledge", tags=["knowledge"])
logger = logging.getLogger(__name__)
_optional_bearer = HTTPBearer(auto_error=False)
_preview_cookie = "kb_preview"


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
        message = error.get("message", "")
    except (ValueError, AttributeError):
        code = ""
        message = ""
    logger.warning("RAG knowledge request failed: status=%s code=%s request_id=%s", response.status_code, code, request_id)
    if response.status_code == 404:
        if code == "DOCUMENT_NOT_FOUND" and "original upload is unavailable" in message:
            return HTTPException(404, detail="原文件未保存，请联系知识库管理员重新上传")
        return HTTPException(404, detail="知识库资源不存在或无权访问")
    if response.status_code == 401:
        return HTTPException(502, detail="知识库服务认证失败")
    return HTTPException(502, detail="知识库服务暂不可用")


async def _json(method: str, path: str, user: User, *, params: dict | None = None, body: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            response = await client.request(method, _url(path), headers=_headers(user), params=params, json=body)
    except httpx.HTTPError as exc:
        logger.warning("RAG knowledge transport failed: %s", type(exc).__name__)
        raise HTTPException(502, detail="无法连接知识库服务") from exc
    if response.is_error:
        raise _upstream_error(response)
    try:
        return response.json()
    except ValueError as exc:
        raise HTTPException(502, detail="知识库服务响应无效") from exc


def _document(row: dict) -> dict:
    filename = row.get("filename", "")
    file_type = PurePath(filename).suffix.lstrip(".").lower()
    return {**row, "file_type": file_type, "preview_available": row.get("preview_available")}


@router.get("/status")
async def status(user: User = Depends(require_role("admin"))):
    return {"mode": "rag"}


@router.get("/collections")
async def collections(limit: int = Query(20, ge=1, le=100), cursor: str | None = None,
                      user: User = Depends(require_role("admin"))):
    return await _json("GET", "/collections", user, params={"limit": limit, "cursor": cursor})


@router.get("/collections/{collection_id}/documents")
async def documents(collection_id: str, limit: int = Query(20, ge=1, le=100), cursor: str | None = None,
                    q: str = "", file_type: str = "", user: User = Depends(require_role("admin"))):
    result = await _json("GET", f"/collections/{_id(collection_id)}/documents", user,
                         params={"limit": limit, "cursor": cursor, "q": q or None, "file_type": file_type or None})
    return {**result, "items": [_document(row) for row in result.get("items", [])]}


class QueryBody(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    mode: str = "hybrid"


@router.post("/collections/{collection_id}/queries")
async def query_collection(collection_id: str, body: QueryBody, user: User = Depends(require_role("admin"))):
    return await _json("POST", f"/collections/{_id(collection_id)}/queries", user, body=body.model_dump())


@router.get("/documents/{document_id}")
async def document_detail(document_id: str, user: User = Depends(require_role("admin"))):
    return _document(await _json("GET", f"/documents/{_id(document_id)}", user))


@router.get("/documents/{document_id}/chunks/{chunk_id}")
async def chunk_detail(document_id: str, chunk_id: str, user: User = Depends(require_role("admin"))):
    return await _json("GET", f"/documents/{_id(document_id)}/chunks/{_id(chunk_id)}", user)


@router.post("/documents/{document_id}/preview-session")
async def create_preview_session(document_id: str, request: Request, user: User = Depends(require_role("admin"))):
    # Check current project authorization before giving the native viewer a cookie.
    await _json("GET", f"/documents/{_id(document_id)}", user)
    try:
        async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
            async with client.stream("GET", _url(f"/documents/{_id(document_id)}/preview"),
                                     headers={**_headers(user), "Range": "bytes=0-0"}) as probe:
                if probe.status_code not in (200, 206):
                    await probe.aread()
                    raise _upstream_error(probe)
    except httpx.HTTPError as exc:
        logger.warning("RAG preview probe failed: %s", type(exc).__name__)
        raise HTTPException(502, detail="无法连接知识库服务") from exc
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    token = jwt.encode({"sub": str(user.id), "doc": document_id, "ver": user.token_version,
                        "type": "knowledge_preview", "exp": expires},
                       settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    response = JSONResponse({"expires_in": 300})
    response.set_cookie(_preview_cookie, token, max_age=300, httponly=True, samesite="lax",
                        secure=request.url.scheme == "https",
                        path=f"/api/v1/knowledge/documents/{_id(document_id)}/file")
    response.headers["Cache-Control"] = "no-store"
    return response


async def _file_user(document_id: str, request: Request,
                     credentials: HTTPAuthorizationCredentials | None = Depends(_optional_bearer),
                     db: AsyncSession = Depends(get_db)) -> User:
    if credentials:
        user = await get_current_user(credentials, db)
    else:
        token = request.cookies.get(_preview_cookie, "")
        payload = decode_token(token)
        if not payload or payload.get("type") != "knowledge_preview" or payload.get("doc") != document_id:
            raise HTTPException(401, detail="预览会话无效或已过期")
        try:
            user_id = int(payload["sub"])
        except (KeyError, TypeError, ValueError) as exc:
            raise HTTPException(401, detail="预览会话无效") from exc
        result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
        user = result.scalar_one_or_none()
        if not user or user.token_version != payload.get("ver"):
            raise HTTPException(401, detail="预览会话无效或已过期")
    if user.role != "admin":
        raise HTTPException(403, detail="无权限访问")
    return user


@router.get("/documents/{document_id}/file")
async def preview(document_id: str, request: Request, user: User = Depends(_file_user)):
    headers = _headers(user)
    if request.headers.get("range"):
        headers["Range"] = request.headers["range"]
    client = httpx.AsyncClient(timeout=httpx.Timeout(15, read=120), trust_env=False)
    try:
        upstream = await client.send(client.build_request("GET", _url(f"/documents/{_id(document_id)}/preview"), headers=headers), stream=True)
    except httpx.HTTPError as exc:
        await client.aclose()
        logger.warning("RAG preview transport failed: %s", type(exc).__name__)
        raise HTTPException(502, detail="无法连接知识库服务") from exc
    if upstream.status_code >= 400 and upstream.status_code != 416:
        await upstream.aread()
        error = _upstream_error(upstream)
        await upstream.aclose()
        await client.aclose()
        raise error

    async def body():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    forwarded = {name: value for name, value in upstream.headers.items() if name.lower() in {
        "content-type", "content-length", "content-range", "accept-ranges", "content-disposition", "etag", "last-modified"
    }}
    forwarded["Cache-Control"] = "private, no-store"
    return StreamingResponse(body(), status_code=upstream.status_code, headers=forwarded)
