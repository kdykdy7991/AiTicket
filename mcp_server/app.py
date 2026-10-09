"""Read-only MCP facade for the ticket API, deployed as its own container."""

import os
import re
import secrets
import logging

import httpx
from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import ToolAnnotations


API_BASE_URL = os.environ.get("TICKET_API_URL", "http://api:8000").rstrip("/")
EXTRA_ALLOWED_HOSTS = [
    host.strip() for host in os.environ.get("MCP_ALLOWED_HOSTS", "").split(",") if host.strip()
]
logger = logging.getLogger("skdy.mcp.auth")


async def _read(path: str, params: dict | None = None) -> dict:
    internal_token = os.environ.get("MCP_INTERNAL_TOKEN", "")
    if not internal_token:
        raise ToolError("工单系统内部连接未配置")
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                f"{API_BASE_URL}/api/v1/internal/mcp{path}",
                params=params,
                headers={"Authorization": f"Bearer {internal_token}"},
            )
        response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 404:
            raise ToolError("未找到对应工单") from exc
        raise ToolError(f"工单系统查询失败（HTTP {exc.response.status_code}）") from exc
    except httpx.HTTPError as exc:
        raise ToolError("暂时无法连接工单系统") from exc
    return response.json()["data"]


mcp = FastMCP(
    "Skdy Ticket Read Only",
    instructions="只读查询客服工单。工具返回的数据可能包含客户个人信息，仅用于当前工单任务。",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        allowed_hosts=[
            "mcp", "mcp:*", "localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*",
            *EXTRA_ALLOWED_HOSTS,
        ],
    ),
)


@mcp.tool(
    description="按工单号、客户姓名、电话或问题描述搜索工单；最多返回 20 条摘要。",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
async def search_tickets(keyword: str, limit: int = 10) -> list[dict]:
    if not 2 <= len(keyword.strip()) <= 100:
        raise ToolError("搜索词长度须为 2 至 100 个字符")
    if not 1 <= limit <= 20:
        raise ToolError("limit 须为 1 至 20")
    return await _read("/tickets", {"keyword": keyword.strip(), "limit": limit})


@mcp.tool(
    description="按工单号查看工单详情、处理流程和处理说明。",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
async def get_ticket(number: str) -> dict:
    if not re.fullmatch(r"[A-Za-z0-9-]{1,20}", number):
        raise ToolError("工单号格式错误")
    return await _read(f"/tickets/{number}")


@mcp.tool(
    description="获取当前启用的工单分类树。",
    annotations=ToolAnnotations(readOnlyHint=True, openWorldHint=False),
)
async def list_categories() -> list[dict]:
    return await _read("/categories")


class BearerProtectedApp:
    """Authenticate every MCP HTTP request before it reaches the SDK."""

    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.inner(scope, receive, send)
            return
        configured = os.environ.get("MCP_BEARER_TOKEN", "")
        headers = dict(scope.get("headers", []))
        scheme, _, token = headers.get(b"authorization", b"").decode("utf-8", errors="ignore").partition(" ")
        # Some platform secret inputs preserve copied leading/trailing whitespace.
        # Normalize only that whitespace; the credential itself must still match.
        normalized_token = token.strip()
        if not configured or scheme.lower() != "bearer" or not secrets.compare_digest(normalized_token, configured):
            logger.warning(
                "MCP authentication rejected: present=%s scheme=%s token_length=%s expected_length=%s whitespace=%s",
                b"authorization" in headers,
                scheme.lower() if scheme else "missing",
                len(token),
                len(configured),
                token != token.strip(),
            )
            body = b'{"error":"Unauthorized"}'
            await send({
                "type": "http.response.start", "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"www-authenticate", b"Bearer"),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.inner(scope, receive, send)


app = BearerProtectedApp(mcp.streamable_http_app())
