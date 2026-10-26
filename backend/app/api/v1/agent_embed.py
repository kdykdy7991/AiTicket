"""Exchange the current ticket user's identity for a one-use Debussy code."""

import re
from urllib.parse import urlsplit

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from fastapi.responses import JSONResponse

from app.core.config import settings
from app.core.deps import require_role
from app.models.user import User

router = APIRouter(prefix="/agent", tags=["agent"])
_APP_PATH = re.compile(r"^/embed/(pub_[0-9a-fA-F-]{36})/?$")


@router.post("/embed/code")
async def create_embed_code(
    origin: str | None = Header(default=None),
    user: User = Depends(require_role("admin")),
):
    """Exchange only a verified ticket user; never expose the client secret."""
    # The agent platform owns the app's allowed origins and iframe CSP. Keep
    # the browser Origin for its exchange check without a second local list.
    if not origin:
        raise HTTPException(400, detail="缺少页面来源信息")
    if not all((settings.AGENT_EMBED_URL, settings.AGENT_EMBED_API_URL,
                settings.AGENT_EMBED_CLIENT_ID, settings.AGENT_EMBED_CLIENT_SECRET)):
        raise HTTPException(503, detail="智能助手尚未完成配置")
    parsed = urlsplit(settings.AGENT_EMBED_URL)
    match = _APP_PATH.fullmatch(parsed.path)
    if parsed.scheme not in ("http", "https") or not parsed.netloc or not match or parsed.query or parsed.fragment:
        raise HTTPException(503, detail="智能助手 Embed 地址配置无效")
    exchange_url = f"{settings.AGENT_EMBED_API_URL.rstrip('/')}/api/embed/v1/auth/exchange"
    try:
        async with httpx.AsyncClient(timeout=8.0, trust_env=False) as client:
            response = await client.post(
                exchange_url,
                headers={"Authorization": f"Bearer {settings.AGENT_EMBED_CLIENT_ID}.{settings.AGENT_EMBED_CLIENT_SECRET}"},
                json={
                    "publicAppId": match.group(1),
                    "origin": origin,
                    "userId": str(user.id),
                    "name": user.name,
                    "roles": ["customer_service" if user.role == "agent" else "admin"],
                },
            )
            response.raise_for_status()
            data = response.json()["data"]
            code, expires_in = data["code"], data["expiresIn"]
            if not isinstance(code, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", code):
                raise ValueError("Invalid exchange code")
            if not isinstance(expires_in, int) or expires_in <= 0:
                raise ValueError("Invalid exchange expiry")
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 403:
            raise HTTPException(403, detail="Agent 平台未允许当前页面来源") from exc
        raise HTTPException(502, detail="智能助手身份交换失败，请稍后重试") from exc
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        raise HTTPException(502, detail="智能助手身份交换失败，请稍后重试") from exc
    return JSONResponse(
        {"data": {"embed_url": settings.AGENT_EMBED_URL,
                  "code": code, "expires_in": expires_in}},
        headers={"Cache-Control": "no-store"},
    )
