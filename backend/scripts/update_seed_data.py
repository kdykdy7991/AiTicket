"""Insert handler users and their skill-group mappings into an existing database.

Only adds users that do not already exist (by id) and their mappings.
Existing dispatchers, categories, skill groups and tickets are left untouched.
"""

import asyncio
import os
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://skdy:skdy123@localhost:5433/skdy_ticket")

engine = create_async_engine(DATABASE_URL, future=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# 默认密码：skdy123
_DEFAULT_HASH = '$2b$12$Oxx10M2ohHR2zd3ekD5WLOll.icytUsKAjpzeoeTu3ZaYvpq0aRKW'

# 对接部门（只确保存在，不删除已有部门）
SKILL_GROUPS = [
    (1, '品牌公关传播'),
    (2, '市场生态部'),
    (3, '产品中心'),
    (4, '网运部'),
    (5, '售后'),
    (6, '客服组'),
]

# 处理人（不覆盖已存在的用户）
HANDLERS = [
    (17, 'jinxin', '金鑫', 'handler', 1, False, _DEFAULT_HASH),
    (18, 'dingxian', '丁晛', 'handler', 1, False, _DEFAULT_HASH),
    (19, 'zhangjingxi', '张景熙', 'handler', 1, False, _DEFAULT_HASH),
    (20, 'xuting', '徐挺', 'handler', 1, False, _DEFAULT_HASH),
    (21, 'wangyan', '王颜', 'handler', 1, False, _DEFAULT_HASH),
    (22, 'jiangchaoyi', '蒋超毅', 'handler', 1, False, _DEFAULT_HASH),
    (23, 'jinjun', '金军', 'handler', 1, False, _DEFAULT_HASH),
    (24, 'jiangweiye', '姜伟业', 'handler', 1, False, _DEFAULT_HASH),
    (25, 'chenwenbing', '陈文兵', 'handler', 1, False, _DEFAULT_HASH),
]

# (user_id, skill_group_id, is_dispatcher)
HANDLER_SKILL_GROUPS = [
    (17, 1, False),  # 金鑫 -> 品牌公关传播
    (18, 1, False),  # 丁晛 -> 品牌公关传播
    (19, 1, False),  # 张景熙 -> 品牌公关传播
    (20, 2, False),  # 徐挺 -> 市场生态部
    (21, 2, False),  # 王颜 -> 市场生态部
    (22, 3, False),  # 蒋超毅 -> 产品中心
    (23, 4, False),  # 金军 -> 网运部
    (24, 5, False),  # 姜伟业 -> 售后
    (25, 5, False),  # 陈文兵 -> 售后
]


async def main() -> None:
    now = datetime.now(timezone.utc)
    async with async_session() as db:
        print("Upserting skill_groups...")
        await db.execute(
            text("""
                INSERT INTO skill_groups (id, name, created_at, updated_at)
                VALUES (:id, :name, :created_at, :updated_at)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name
            """),
            [
                {"id": sg[0], "name": sg[1], "created_at": now, "updated_at": now}
                for sg in SKILL_GROUPS
            ],
        )

        print("Inserting handler users...")
        # 先查已存在的 username / name，避免唯一约束冲突
        existing_rows = (await db.execute(text("SELECT username, name FROM users"))).all()
        existing_usernames = {row[0] for row in existing_rows}
        existing_names = {row[1] for row in existing_rows}
        handlers_to_insert = [
            u for u in HANDLERS
            if u[1] not in existing_usernames and u[2] not in existing_names
        ]
        for u in handlers_to_insert:
            await db.execute(
                text("""
                    INSERT INTO users (id, username, name, role, group_id, is_group_leader, password_hash, is_active, created_at, updated_at)
                    VALUES (:id, :username, :name, :role, :group_id, :is_group_leader, :password_hash, :is_active, :created_at, :updated_at)
                    ON CONFLICT (id) DO NOTHING
                """),
                {
                    "id": u[0], "username": u[1], "name": u[2], "role": u[3],
                    "group_id": u[4], "is_group_leader": u[5], "password_hash": u[6],
                    "is_active": True, "created_at": now, "updated_at": now,
                },
            )

        print("Inserting handler skill-group mappings...")
        # 只给确实存在的用户插关联
        user_id_result = await db.execute(text("SELECT id FROM users WHERE id = ANY(:ids)"), {"ids": [u[0] for u in HANDLERS]})
        existing_user_ids = {row[0] for row in user_id_result.all()}
        mappings_to_insert = [
            usg for usg in HANDLER_SKILL_GROUPS
            if usg[0] in existing_user_ids
        ]
        await db.execute(
            text("""
                INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher)
                VALUES (:user_id, :skill_group_id, :is_dispatcher)
                ON CONFLICT DO NOTHING
            """),
            [
                {"user_id": usg[0], "skill_group_id": usg[1], "is_dispatcher": usg[2]}
                for usg in mappings_to_insert
            ],
        )

        await db.commit()
        print("Done.")


if __name__ == "__main__":
    asyncio.run(main())
