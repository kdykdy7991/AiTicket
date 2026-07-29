"""Pytest fixtures: isolated test DB, per-test cleanup, auth override.

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
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

# 确保 backend/ 在 sys.path 上，使 `app` 可导入
BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))

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

TEST_DATABASE_URL = os.environ.get(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://skdy:skdy123@localhost:5433/skdy_ticket_test",
)
_DB_NAME = "skdy_ticket_test"
# 维护连接：连 postgres 库以执行 CREATE/DROP DATABASE
_ADMIN_DSN = TEST_DATABASE_URL.replace("/skdy_ticket_test", "/postgres").replace(
    "postgresql+asyncpg://", "postgresql://"
)


async def _recreate_test_db() -> None:
    """每次 session 重建测试库，保证干净。"""
    conn = await asyncpg.connect(_ADMIN_DSN)
    try:
        await conn.execute(f"DROP DATABASE IF EXISTS {_DB_NAME}")
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


@pytest_asyncio.fixture
async def client():
    """返回 (AsyncClient, dispatcher_id, engine)。

    - override get_db 指向测试库 session
    - override get_current_user 返回测试 admin 用户（绕过 JWT）
    - 预置一个 admin(creator) + 一个 dispatcher 用户
    - 测试结束后 TRUNCATE 所有表，数据不残留
    """
    engine = create_async_engine(TEST_DATABASE_URL)
    Session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # 预置用户
    async with Session() as s:
        from app.models.user import User

        admin = User(username="test-admin", name="管理员", password_hash="x", role="admin")
        disp = User(username="test-dispatcher", name="对接人", password_hash="x", role="agent")
        s.add_all([admin, disp])
        await s.commit()
        await s.refresh(admin)
        await s.refresh(disp)
        admin_id, dispatcher_id = admin.id, disp.id

    async def override_get_db():
        async with Session() as s:
            try:
                yield s
                if s.in_transaction():
                    await s.commit()
            except Exception:
                await s.rollback()
                raise

    # 构造 detached 用户实例供依赖注入；create_ticket 只用到 id / group_id / role
    fake_user = type(
        "_FakeUser",
        (),
        {"id": admin_id, "group_id": None, "role": "admin", "is_active": True},
    )()

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = lambda: fake_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c, dispatcher_id, engine

    app.dependency_overrides.clear()
    tables = ", ".join(f'"{n}"' for n in Base.metadata.tables)
    async with engine.begin() as conn:
        await conn.execute(text(f"TRUNCATE {tables} RESTART IDENTITY CASCADE"))
    await engine.dispose()
