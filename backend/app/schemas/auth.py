"""Pydantic schemas for authentication."""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.common import SkillGroupRef


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, description="登录名")
    password: str = Field(..., min_length=1, description="密码")


class RefreshRequest(BaseModel):
    refresh_token: str


class ChangePasswordRequest(BaseModel):
    old_password: str = Field(..., min_length=1, description="原密码")
    new_password: str = Field(..., min_length=6, max_length=64, description="新密码，至少 6 位")


class UserInfo(BaseModel):
    """POC 登录用户信息。旧的客服组/组长字段不再返回。"""

    id: int
    username: str
    name: str
    #: 一个用户可拥有多个业务角色（多角色）
    roles: list[str] = Field(default_factory=list)
    skill_groups: list[SkillGroupRef] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True)


class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserInfo
