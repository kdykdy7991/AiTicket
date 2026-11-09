"""FastAPI dependencies: current user, database session."""

import re

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.permissions import (
    READ_GRANT_KEYS, feature_access_allowed, full_read_allowed, has_grant,
    load_grants, read_grant_allowed,
)
from app.core.security import decode_token
from app.models.user import User

bearer_scheme = HTTPBearer()


async def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    """Decode JWT and return the User object."""
    payload = decode_token(credentials.credentials)
    if payload is None or payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="无效的认证凭证")

    user_id = int(payload["sub"])
    result = await db.execute(select(User).where(User.id == user_id, User.is_active == True))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="用户不存在或已禁用")

    # 会话版本校验：每次登录版本 +1，旧会话的 access token（版本落后）立即失效，
    # 实现"一个账号同时只能一人在线"（后登录者顶掉前者）
    if payload.get("ver", 0) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="该账号已在其他设备登录，请重新登录",
        )

    # Grants are resolved from the DB on every request, so an administrator's
    # change in user management takes effect without requiring a new login on
    # the backend side.
    await load_grants(db, user)

    # A viewer can inspect data but cannot take part in any business or
    # administration workflow. Keep the guard here so new write endpoints
    # cannot accidentally grant access through a permissive dependency.
    if user.role in {"department_leader", "division_leader"}:
        path, method = request.url.path, request.method
        account = path in {"/api/v1/auth/me", "/api/v1/auth/logout", "/api/v1/auth/change-password"}
        listing = method == "GET" and path in {"/api/v1/tickets", "/api/v1/tickets/export", "/api/v1/categories"}
        match = re.fullmatch(r"/api/v1/tickets/(\d+)(?:/(current-form|node-submissions|node-submit|state-logs|articles))?", path)
        allowed = {("GET", None), ("PATCH", None), ("GET", "current-form"),
                   ("GET", "node-submissions"), ("GET", "state-logs"),
                   ("GET", "articles"), ("POST", "articles"), ("POST", "node-submit")}
        if match and (method, match.group(2)) in allowed:
            from app.models.ticket import Ticket
            ticket = await db.get(Ticket, int(match.group(1)))
            steps = ticket.dispatch_chain_steps or [] if ticket else []
            index = (ticket.dispatch_step_index or 0) if ticket else 0
            own_complaint = (ticket is not None and not ticket.is_draft and ticket.owner_id == user.id
                             and ticket.category_id in (2102, 2103, 2104)
                             and 0 <= index < len(steps) and steps[index].get("complaint_direct"))
            if own_complaint:
                return user
        # Holding every read domain keeps the legacy broad GET behaviour;
        # individual domains only bypass the leader allowlist for endpoints
        # declared in READ_GRANT_ENDPOINTS. Feature grants match exactly.
        capability_allowed = (
            full_read_allowed(user, method, path)
            or read_grant_allowed(user, method, path, READ_GRANT_KEYS)
            or feature_access_allowed(user, method, path)
        )
        if not account and not listing and not capability_allowed:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="仅可访问本人负责的投诉工单")

    if user.role == "observer" and request.method not in {"GET", "HEAD", "OPTIONS"}:
        path = request.url.path
        read_only_post = (
            request.method == "POST"
            and path.startswith("/api/v1/knowledge/collections/")
            and path.endswith("/queries")
        )
        own_account_post = request.method == "POST" and path in {
            "/api/v1/auth/logout", "/api/v1/auth/change-password",
        }
        if not (read_only_post or own_account_post):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="观察员只能查看数据")

    return user


def require_role(
    *roles: str,
    allow_read_grants: tuple[str, ...] = (),
    allow_grants: tuple[str, ...] = (),
):
    """Dependency factory: restrict access to specified roles.

    ``allow_read_grants`` declares which read-domain capabilities unlock this
    endpoint. Every such endpoint must be listed in ``READ_GRANT_ENDPOINTS``;
    there is no longer any inference from the ``"observer"`` string in roles.
    ``allow_grants`` does the same for feature-entry capabilities.
    """
    async def _check(request: Request, user: User = Depends(get_current_user)):
        if user.role in roles:
            return user
        method, path = request.method, request.url.path
        read_access = read_grant_allowed(user, method, path, allow_read_grants)
        grant_access = (
            bool(allow_grants)
            and feature_access_allowed(user, method, path)
            and any(has_grant(user, key) for key in allow_grants)
        )
        if not read_access and not grant_access:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="无权限访问")
        return user
    return _check
