"""Pytest fixtures: isolated test DB, POC fixture data, per-test cleanup, auth override.

测试库走环境变量 TEST_DATABASE_URL，默认连开发 db(localhost:5433)的独立库
skdy_ticket_test，不碰开发/生产数据。前提：本机已起 db 容器：
    docker compose -f backend/docker-compose.yml up -d db
"""

import asyncio
import os
import sys
from pathlib import Path

import asyncpg
import pytest
import pytest_asyncio
from alembic import command
from alembic.config import Config
from fastapi import Depends
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 确保 backend/ 在 sys.path 上，使 `app` 可导入
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

from app.core.config import settings  # noqa: E402
from app.core.database import Base, get_db  # noqa: E402
from app.core.deps import get_current_user  # noqa: E402
from app.main import app  # noqa: E402
from app.models import (  # noqa: E402,F401  注册所有表到 Base.metadata
    audit,
    category,
    group,
    notification,
    sla,
    ticket,
    user,
)
from app.models.group import SkillGroup, UserSkillGroup  # noqa: E402
from app.models.user import User, UserRole  # noqa: E402

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://skdy:skdy123@localhost:5433/skdy_ticket_test",
)
_DB_NAME = "skdy_ticket_test"
# 维护连接：连 postgres 库以执行 CREATE/DROP DATABASE
_ADMIN_DSN = TEST_DATABASE_URL.replace("/skdy_ticket_test", "/postgres").replace(
    "postgresql+asyncpg://", "postgresql://"
)

#: 联调测试账号统一密码，对应下面的 bcrypt 哈希
FIXTURE_PASSWORD = "skdy123"
_FIXTURE_HASH = "$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O"

#: 五个分系统
SKILL_GROUP_NAMES = ("系统总体", "卫星平台", "终端系统", "应用平台", "测运控平台")

#: (username, name, roles, 分系统名 | None)；一个用户可以有多个业务角色
FIXTURE_USERS = [
    ("admin", "系统管理员", ["admin"], None),
    ("presales01", "售前-张伟", ["presales"], None),
    ("presales02", "售前-李娜", ["presales"], None),
    ("approver01", "邱庆举", ["approver"], None),
    ("approver02", "备用批准人", ["approver"], None),
    ("taskforce01", "陈毅君", ["taskforce"], None),
    ("subsystem01", "邓雪群", ["taskforce", "subsystem"], "系统总体"),
    ("subsystem06", "系统总体-同事", ["subsystem"], "系统总体"),
    ("subsystem02", "卢翔", ["subsystem"], "卫星平台"),
    ("subsystem03", "余华伟", ["subsystem"], "终端系统"),
    ("quality01", "金凯", ["quality"], None),
    ("Tony", "领导账号一", ["leader"], None),
    ("Edison", "领导账号二", ["leader"], None),
    # 多角色用户：既是批准人，又是系统总体负责人
    ("multi01", "多角色-邱庆举", ["approver", "subsystem"], "系统总体"),
]


async def _recreate_test_db() -> None:
    """每次 session 重建测试库，保证干净。"""
    conn = await asyncpg.connect(_ADMIN_DSN)
    try:
        await conn.execute(f"DROP DATABASE IF EXISTS {_DB_NAME} WITH (FORCE)")
        await conn.execute(f"CREATE DATABASE {_DB_NAME}")
    finally:
        await conn.close()


def _run_migrations() -> None:
    """用 alembic upgrade head 建表（与生产 schema 一致）。"""
    os.environ["DATABASE_URL"] = TEST_DATABASE_URL
    cfg = Config(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("sqlalchemy.url", TEST_DATABASE_URL)
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session", autouse=True)
def _setup_db():
    """session 级：建测试库 + 跑 migration。"""
    asyncio.run(_recreate_test_db())
    _run_migrations()
    yield


class ApiHarness:
    """测试客户端 + 切换当前登录用户 + 直连数据库断言。"""

    def __init__(self, client: AsyncClient, session_factory, engine):
        self.c = client
        self._session_factory = session_factory
        self.engine = engine
        self.users: dict[str, int] = {}
        self.skill_groups: dict[str, int] = {}
        self._current = "presales01"

    # -- 身份 -------------------------------------------------
    def as_(self, username: str) -> None:
        assert username in self.users, f"未知测试账号 {username}"
        self._current = username

    @property
    def current(self) -> str:
        return self._current

    def uid(self, username: str) -> int:
        return self.users[username]

    def sg(self, name: str) -> int:
        return self.skill_groups[name]

    # -- 数据库 -----------------------------------------------
    def session(self) -> AsyncSession:
        return self._session_factory()

    # -- HTTP 便捷方法 ----------------------------------------
    async def create_ticket(self, *, draft: bool = False, **overrides):
        payload = {
            "title": "POC 现场终端掉线",
            "proposer": "张三",
            "proposer_department": "售前与解决方案部",
            "product_line": "卫星通信终端",
            "customer_name": "某省应急厅",
            "priority": "p2_normal",
            "problem_type": "终端故障",
            "closure_requirement": "两周内闭环",
            "occurred_at": "2026-09-01T08:30:00+08:00",
            "location": "广东省深圳市南山区",
            "device_info": "终端型号 X1 / SN 0001 / 固件 3.2.1",
            "description": "现场终端反复掉线，重启后恢复",
            "approver_id": self.uid("approver01"),
        }
        payload.update(overrides)
        payload["is_draft"] = draft
        return await self.c.post("/api/v1/tickets", json=payload)

    async def detail(self, ticket_id: int, expect: int = 200) -> dict:
        resp = await self.c.get(f"/api/v1/tickets/{ticket_id}")
        assert resp.status_code == expect, resp.text
        return resp.json()

    async def action(
        self,
        ticket_id: int,
        action: str,
        *,
        payload: dict | None = None,
        comment: str | None = None,
        version: int | None = None,
        expect: int = 200,
    ):
        if version is None:
            # 无查看权限的越权用例拿不到 version，用一个占位值即可：
            # 服务端先做可见性判断，再做版本判断。
            probe = await self.c.get(f"/api/v1/tickets/{ticket_id}")
            payload_json = probe.json()
            version = payload_json.get("state_version", 1) if probe.status_code == 200 else 1
        body: dict = {"action": action, "payload": payload or {}, "expected_version": version}
        if comment is not None:
            body["comment"] = comment
        resp = await self.c.post(f"/api/v1/tickets/{ticket_id}/actions", json=body)
        assert resp.status_code == expect, resp.text
        return resp

    async def acted(self, ticket_id: int, action: str, **kwargs) -> dict:
        """执行动作并返回 TicketDetail JSON。"""
        resp = await self.action(ticket_id, action, **kwargs)
        return resp.json()


@pytest_asyncio.fixture
async def api(tmp_path_factory, monkeypatch):
    """POC 联调夹具：五个业务角色账号 + 五个分系统。"""
    upload_dir = tmp_path_factory.mktemp("uploads")
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_dir))

    engine = create_async_engine(TEST_DATABASE_URL)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    harness_holder: dict = {}

    async with Session() as s:
        skill_groups: dict[str, int] = {}
        for name in SKILL_GROUP_NAMES:
            sg = SkillGroup(name=name, dingtalk_webhook_url=None)
            s.add(sg)
            await s.flush()
            skill_groups[name] = sg.id

        users: dict[str, int] = {}
        memberships: list[tuple[str, str]] = []
        for username, name, roles, sg_name in FIXTURE_USERS:
            u = User(username=username, name=name, password_hash=_FIXTURE_HASH, is_active=True)
            s.add(u)
            await s.flush()
            users[username] = u.id
            for role in roles:
                s.add(UserRole(user_id=u.id, role=role))
            if sg_name:
                memberships.append((username, sg_name))
        for username, sg_name in memberships:
            s.add(
                UserSkillGroup(
                    user_id=users[username],
                    skill_group_id=skill_groups[sg_name],
                    is_dispatcher=False,
                )
            )
        await s.commit()

    auth_state = {"username": "presales01"}

    async def override_get_db():
        async with Session() as s:
            try:
                yield s
                if s.in_transaction():
                    await s.commit()
            except Exception:
                await s.rollback()
                raise

    async def override_current_user(db: AsyncSession = Depends(get_db)):
        result = await db.execute(
            select(User).where(User.username == auth_state["username"])
        )
        return result.scalar_one()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        harness = ApiHarness(client, Session, engine)
        harness.users = users
        harness.skill_groups = skill_groups
        harness_holder["harness"] = harness

        original_as = harness.as_

        def as_(username: str) -> None:
            auth_state["username"] = username
            original_as(username)

        harness.as_ = as_  # type: ignore[method-assign]
        yield harness

    app.dependency_overrides.clear()
    tables = ", ".join(f'"{n}"' for n in Base.metadata.tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()
