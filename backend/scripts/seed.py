"""POC 质量问题闭环：幂等种子数据。

在 `alembic upgrade head` 之后执行，写入：
- 五个分系统（skill_groups）
- 六个角色（含隐藏管理员）的联调账号
- subsystem 用户与分系统的关联

可重复执行：按 username / name 做 upsert，不会产生重复数据，也不会改动已有工单。
"""

import asyncio
import os

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get(
    "DATABASE_URL", "postgresql+asyncpg://skdy:skdy123@localhost:5433/skdy_ticket"
)

engine = create_async_engine(DATABASE_URL, future=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

REGIONS = [
    # 一级：省/直辖市
    (110000, None, "北京市", 1, "110000", 1),
    (120000, None, "天津市", 1, "120000", 2),
    (310000, None, "上海市", 1, "310000", 3),
    (440000, None, "广东省", 1, "440000", 4),
    (320000, None, "江苏省", 1, "320000", 5),
    (330000, None, "浙江省", 1, "330000", 6),
    # 二级：市
    (110100, 110000, "北京市", 2, "110100", 1),
    (310100, 310000, "上海市", 2, "310100", 3),
    (440100, 440000, "广州市", 2, "440100", 4),
    (440300, 440000, "深圳市", 2, "440300", 5),
    (320100, 320000, "南京市", 2, "320100", 6),
    (330100, 330000, "杭州市", 2, "330100", 8),
]

# 默认组（用户归属，不参与 POC 业务流转）
GROUPS = [(1, "默认组")]

# 五个分系统（前端展示为“分系统”）
SKILL_GROUPS = [
    "系统总体",
    "卫星平台",
    "终端系统",
    "应用平台",
    "测运控平台",
]

# 默认密码：admin 为 admin123，其余业务账号为 skdy123
_ADMIN_HASH = "$2b$12$Oxx10M2ohHR2zd3ekD5WLOll.icytUsKAjpzeoeTu3ZaYvpq0aRKW"
_SKDY_HASH = "$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O"

# (username, name, role, skill_group_name | None)
USERS = [
    ("admin", "系统管理员", "admin", None),
    ("presales01", "售前-张伟", "presales", None),
    ("presales02", "售前-李娜", "presales", None),
    ("approver01", "邱庆举", "approver", None),
    ("taskforce01", "陈毅君", "taskforce", None),
    ("subsystem01", "邓雪群", "subsystem", "系统总体"),
    ("subsystem02", "卢翔", "subsystem", "卫星平台"),
    ("subsystem03", "余华伟", "subsystem", "终端系统"),
    ("subsystem04", "邱庆举", "subsystem", "应用平台"),
    ("subsystem05", "倪汉华", "subsystem", "测运控平台"),
    ("quality01", "金凯", "quality", None),
    ("quality02", "马祥艺", "quality", None),
    ("quality03", "巫雪峰", "quality", None),
]


async def _resync_sequences(db: AsyncSession) -> None:
    """把自增序列对齐到当前最大 id。

    老库里的数据是用显式 id 插入的，序列可能落后，导致新插入主键冲突。
    """
    for table in ("regions", "groups", "skill_groups", "users", "ticket_categories"):
        await db.execute(
            text(
                f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM {table}), 1))"
            )
        )


async def seed() -> None:
    async with async_session() as db:
        # 先对齐序列，避免显式 id 历史数据导致新插入主键冲突
        await _resync_sequences(db)

        print("Seeding regions...")
        await db.execute(
            text(
                """
                INSERT INTO regions (id, parent_id, name, level, code, sort_order, is_active, created_at, updated_at)
                VALUES (:id, :parent_id, :name, :level, :code, :sort_order, true, now(), now())
                ON CONFLICT (id) DO NOTHING
                """
            ),
            [
                {
                    "id": r[0], "parent_id": r[1], "name": r[2],
                    "level": r[3], "code": r[4], "sort_order": r[5],
                }
                for r in REGIONS
            ],
        )

        print("Seeding groups...")
        await db.execute(
            text(
                """
                INSERT INTO groups (id, name, created_at, updated_at)
                VALUES (:id, :name, now(), now())
                ON CONFLICT (id) DO NOTHING
                """
            ),
            [{"id": g[0], "name": g[1]} for g in GROUPS],
        )

        print("Seeding skill groups (分系统)...")
        await db.execute(
            text(
                """
                INSERT INTO skill_groups (name, created_at, updated_at)
                VALUES (:name, now(), now())
                ON CONFLICT (name) DO NOTHING
                """
            ),
            [{"name": name} for name in SKILL_GROUPS],
        )

        print("Upserting POC users...")
        for username, name, role, _sg in USERS:
            password_hash = _ADMIN_HASH if username == "admin" else _SKDY_HASH
            await db.execute(
                text(
                    """
                    INSERT INTO users
                        (username, name, role, group_id, is_group_leader, password_hash,
                         is_active, token_version, created_at, updated_at)
                    VALUES
                        (:username, :name, :role, 1, false, :password_hash, true, 0, now(), now())
                    ON CONFLICT (username) DO UPDATE
                       SET name = EXCLUDED.name,
                           role = EXCLUDED.role,
                           password_hash = EXCLUDED.password_hash,
                           is_active = true,
                           updated_at = now()
                    """
                ),
                {
                    "username": username,
                    "name": name,
                    "role": role,
                    "password_hash": password_hash,
                },
            )

        print("Upserting subsystem memberships...")
        for username, _name, role, skill_group in USERS:
            if role != "subsystem" or not skill_group:
                continue
            await db.execute(
                text(
                    """
                    INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher)
                    SELECT u.id, s.id, false
                      FROM users u, skill_groups s
                     WHERE u.username = :username AND s.name = :skill_group
                    ON CONFLICT DO NOTHING
                    """
                ),
                {"username": username, "skill_group": skill_group},
            )

        # 插入后再次对齐序列
        await _resync_sequences(db)

        await db.commit()

        rows = (
            await db.execute(
                text("SELECT username, name, role FROM users ORDER BY id")
            )
        ).all()
        print("Seed completed. Accounts:")
        for username, name, role in rows:
            print(f"  - {username:14s} {name:8s} {role}")


if __name__ == "__main__":
    asyncio.run(seed())
