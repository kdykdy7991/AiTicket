"""Auth router — login, refresh, logout."""

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, LoginResponse, RefreshRequest, ChangePasswordRequest, UserInfo

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=LoginResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)):
    """用户登录，返回 JWT access + refresh token。"""
    result = await db.execute(
        select(User).where(User.username == body.username, User.is_active == True)
    )
    user = result.scalar_one_or_none()

    if user is None or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误",
        )

    # 更新最后登录时间 + 会话版本 +1（原子操作）。
    # 版本 +1 使该账号之前的 token 全部失效，实现"一个账号同时只能一人在线"。
    result = await db.execute(
        update(User).where(User.id == user.id).values(
            last_login_at=datetime.now(timezone.utc),
            token_version=User.token_version + 1,
        ).returning(User.token_version)
    )
    token_version = result.scalar_one()
    await db.commit()

    access_token = create_access_token(user.id, user.roles, token_version)
    refresh_token = create_refresh_token(user.id, token_version)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=1800,
        user=UserInfo.model_validate(user),
    )


@router.post("/auth/refresh", response_model=LoginResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)):
    """刷新 Token。"""
    payload = decode_token(body.refresh_token)
    if payload is None or payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的刷新凭证",
        )

    user_id = int(payload["sub"])
    result = await db.execute(
        select(User).where(User.id == user_id, User.is_active == True)
    )
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在或已禁用",
        )

    # 会话版本校验：登录会使版本 +1，旧会话的 refresh token（版本落后）不再可刷新
    if payload.get("ver", 0) != user.token_version:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="该账号已在其他设备登录，请重新登录",
        )

    access_token = create_access_token(user.id, user.roles, user.token_version)
    refresh_token = create_refresh_token(user.id, user.token_version)

    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=1800,
        user=UserInfo.model_validate(user),
    )


@router.post("/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(user: User = Depends(get_current_user)):
    """登出。一期简单实现：客户端删除 token 即可。"""
    # TODO: 二期可将 token 加入 Redis 黑名单
    return None


@router.post("/auth/change-password")
async def change_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """修改当前登录用户自己的密码。

    校验原密码后直接更新 password_hash。JWT 是无状态的，改密不影响已签发 token，
    用户可继续使用当前会话。
    """
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误",
        )
    if body.old_password == body.new_password:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="新密码不能与原密码相同",
        )
    user.password_hash = hash_password(body.new_password)
    await db.commit()
    return {"message": "密码修改成功"}
