"""Pydantic schemas for authentication."""

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="登录名")
    password: str = Field(..., min_length=1, description="密码")


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, description="原密码")
    new_password: str = Field(..., min_length=6, max_length=64, description="新密码，至少 6 位")


class UserInfo(BaseModel):
    id: int
    username: str
    name: str
    role: str
    group_id: int | None = None
    is_group_leader: bool = False

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo
