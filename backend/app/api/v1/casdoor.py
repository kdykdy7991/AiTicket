"""Casdoor OIDC authorization-code login for existing ticket accounts."""

import re
import base64
import hashlib
import logging
from datetime import datetime, timezone
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, HTTPException
from jose import JWTError, jwt
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import create_access_token, create_refresh_token
from app.models.user import User
from app.schemas.auth import LoginResponse, UserInfo

router = APIRouter(prefix="/auth/casdoor", tags=["auth"])
logger = logging.getLogger(__name__)
_VERIFIER = re.compile(r"^[A-Za-z0-9._~-]{43,128}$")
_REDIRECT_PATH = "/auth/casdoor/callback"


class ExchangeRequest(BaseModel):
    code: str = Field(min_length=1, max_length=2048)
    code_verifier: str = Field(min_length=43, max_length=128)
    nonce: str = Field(min_length=16, max_length=128)
    redirect_uri: str


class ChallengeRequest(BaseModel):
    code_verifier: str = Field(min_length=43, max_length=128)


def _configured() -> bool:
    return all((settings.CASDOOR_ISSUER, settings.CASDOOR_CLIENT_ID,
                settings.CASDOOR_CLIENT_SECRET, settings.CASDOOR_REDIRECT_ORIGINS))


def _redirect_allowed(uri: str) -> bool:
    parsed = urlsplit(uri)
    if parsed.scheme not in ("http", "https") or parsed.query or parsed.fragment:
        return False
    if parsed.path != _REDIRECT_PATH:
        return False
    allowed = {item.strip().rstrip("/") for item in settings.CASDOOR_REDIRECT_ORIGINS.split(",") if item.strip()}
    return f"{parsed.scheme}://{parsed.netloc}" in allowed


async def _discovery(client: httpx.AsyncClient) -> dict:
    issuer = settings.CASDOOR_ISSUER.rstrip("/")
    response = await client.get(f"{issuer}/.well-known/openid-configuration")
    response.raise_for_status()
    data = response.json()
    if data.get("issuer") != issuer:
        raise ValueError("OIDC issuer mismatch")
    for key in ("authorization_endpoint", "token_endpoint", "jwks_uri"):
        endpoint = data.get(key)
        if not isinstance(endpoint, str) or urlsplit(endpoint).netloc != urlsplit(issuer).netloc:
            raise ValueError(f"Invalid OIDC {key}")
    return data


@router.get("/config")
async def casdoor_config():
    if not _configured():
        return {"enabled": False}
    try:
        async with httpx.AsyncClient(timeout=5.0, trust_env=False) as client:
            data = await _discovery(client)
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        raise HTTPException(503, detail="Casdoor 暂时不可用") from exc
    return {
        "enabled": True,
        "authorization_endpoint": data["authorization_endpoint"],
        "client_id": settings.CASDOOR_CLIENT_ID,
        "redirect_origins": [value.strip().rstrip("/") for value in settings.CASDOOR_REDIRECT_ORIGINS.split(",") if value.strip()],
    }


@router.post("/challenge")
async def casdoor_challenge(body: ChallengeRequest):
    """Compute PKCE S256 for HTTP LAN development, where WebCrypto is unavailable."""
    if not _configured() or not _VERIFIER.fullmatch(body.code_verifier):
        raise HTTPException(400, detail="Casdoor 登录请求无效")
    digest = hashlib.sha256(body.code_verifier.encode("ascii")).digest()
    return {"challenge": base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")}


async def _verified_subject(body: ExchangeRequest) -> str:
    if not _configured():
        raise HTTPException(503, detail="Casdoor 登录尚未配置")
    if not _redirect_allowed(body.redirect_uri) or not _VERIFIER.fullmatch(body.code_verifier):
        raise HTTPException(400, detail="Casdoor 登录请求无效")
    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            discovery = await _discovery(client)
            token_response = await client.post(
                discovery["token_endpoint"],
                data={
                    "grant_type": "authorization_code",
                    "code": body.code,
                    "redirect_uri": body.redirect_uri,
                    "client_id": settings.CASDOOR_CLIENT_ID,
                    "client_secret": settings.CASDOOR_CLIENT_SECRET,
                    "code_verifier": body.code_verifier,
                },
            )
            token_response.raise_for_status()
            token_data = token_response.json()
            id_token = token_data["id_token"]
            access_token = token_data["access_token"]
            jwks_response = await client.get(discovery["jwks_uri"])
            jwks_response.raise_for_status()
            claims = jwt.decode(
                id_token,
                jwks_response.json(),
                algorithms=["RS256", "RS512", "ES256", "ES384", "ES512"],
                audience=settings.CASDOOR_CLIENT_ID,
                issuer=settings.CASDOOR_ISSUER.rstrip("/"),
                access_token=access_token,
            )
    except (httpx.HTTPStatusError, KeyError, ValueError, JWTError) as exc:
        logger.warning("Casdoor OIDC exchange validation failed: %s: %s", type(exc).__name__, exc)
        raise HTTPException(401, detail="Casdoor 身份验证失败") from exc
    except httpx.HTTPError as exc:
        raise HTTPException(503, detail="Casdoor 暂时不可用") from exc
    subject = claims.get("sub")
    if claims.get("nonce") != body.nonce or not isinstance(subject, str) or not subject:
        logger.warning("Casdoor OIDC claims validation failed: nonce_match=%s, subject_present=%s",
                       claims.get("nonce") == body.nonce, isinstance(subject, str) and bool(subject))
        raise HTTPException(401, detail="Casdoor 身份验证失败")
    return subject


@router.post("/link")
async def link_casdoor(
    body: ExchangeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Pilot binding: only the currently signed-in ticket admin can link self."""
    if user.role != "admin":
        raise HTTPException(403, detail="目前仅管理员可绑定 Casdoor")
    subject = await _verified_subject(body)
    issuer = settings.CASDOOR_ISSUER.rstrip("/")
    existing = (await db.execute(select(User).where(
        User.casdoor_issuer == issuer, User.casdoor_subject == subject,
    ))).scalar_one_or_none()
    if existing is not None and existing.id != user.id:
        raise HTTPException(409, detail="该 Casdoor 账号已绑定其他工单用户")
    local = (await db.execute(select(User).where(User.id == user.id))).scalar_one()
    if local.casdoor_subject and (local.casdoor_subject != subject or local.casdoor_issuer != issuer):
        raise HTTPException(409, detail="当前工单账号已绑定其他 Casdoor 账号")
    local.casdoor_issuer = issuer
    local.casdoor_subject = subject
    await db.commit()
    return {"bound": True, "username": local.username}


@router.post("/exchange", response_model=LoginResponse)
async def login_with_casdoor(body: ExchangeRequest, db: AsyncSession = Depends(get_db)):
    subject = await _verified_subject(body)
    user = (await db.execute(select(User).where(
        User.casdoor_issuer == settings.CASDOOR_ISSUER.rstrip("/"),
        User.casdoor_subject == subject,
        User.is_active == True,
    ))).scalar_one_or_none()
    if user is None:
        raise HTTPException(403, detail="该 Casdoor 账号尚未绑定启用中的工单账号")
    version = (await db.execute(
        update(User).where(User.id == user.id).values(
            last_login_at=datetime.now(timezone.utc),
            token_version=User.token_version + 1,
        ).returning(User.token_version)
    )).scalar_one()
    await db.commit()
    return LoginResponse(
        access_token=create_access_token(user.id, user.role, version),
        refresh_token=create_refresh_token(user.id, version),
        expires_in=1800,
        user=UserInfo.model_validate(user),
    )
