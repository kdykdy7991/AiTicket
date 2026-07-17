"""Idempotent seed data for fresh deployments.

Run after `alembic upgrade head` to populate default regions and test users.
Safe to run multiple times (uses ON CONFLICT DO NOTHING).
"""

import asyncio
import os
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql+asyncpg://skdy:skdy123@localhost:5433/skdy_ticket")

engine = create_async_engine(DATABASE_URL, future=True)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

REGIONS = [
    # 一级：省/直辖市
    (110000, None, '北京市', 1, '110000', 1),
    (120000, None, '天津市', 1, '120000', 2),
    (310000, None, '上海市', 1, '310000', 3),
    (440000, None, '广东省', 1, '440000', 4),
    (320000, None, '江苏省', 1, '320000', 5),
    (330000, None, '浙江省', 1, '330000', 6),
    # 二级：市
    (110100, 110000, '北京市', 2, '110100', 1),
    (120100, 120000, '天津市', 2, '120100', 2),
    (310100, 310000, '上海市', 2, '310100', 3),
    (440100, 440000, '广州市', 2, '440100', 4),
    (440300, 440000, '深圳市', 2, '440300', 5),
    (320100, 320000, '南京市', 2, '320100', 6),
    (320500, 320000, '苏州市', 2, '320500', 7),
    (330100, 330000, '杭州市', 2, '330100', 8),
    (330200, 330000, '宁波市', 2, '330200', 9),
    # 三级：区县
    (110105, 110100, '朝阳区', 3, '110105', 1),
    (110108, 110100, '海淀区', 3, '110108', 2),
    (110101, 110100, '东城区', 3, '110101', 3),
    (120101, 120100, '和平区', 3, '120101', 4),
    (310104, 310100, '徐汇区', 3, '310104', 5),
    (310115, 310100, '浦东新区', 3, '310115', 6),
    (440106, 440100, '天河区', 3, '440106', 7),
    (440105, 440100, '海珠区', 3, '440105', 8),
    (440305, 440300, '南山区', 3, '440305', 9),
    (440304, 440300, '福田区', 3, '440304', 10),
    (320102, 320100, '玄武区', 3, '320102', 11),
    (320505, 320500, '虎丘区', 3, '320505', 12),
    (330102, 330100, '上城区', 3, '330102', 13),
    (330106, 330100, '西湖区', 3, '330106', 14),
    (330203, 330200, '海曙区', 3, '330203', 15),
]

GROUPS = [
    (1, '默认组'),
]

SKILL_GROUPS = [
    (1, '品牌公关传播'),
    (2, '市场生态部'),
    (3, '产品中心'),
    (4, '网运部'),
    (5, '售后'),
    (6, '客服组'),
]

# 默认密码：skdy123
_DEFAULT_HASH = '$2b$12$Oxx10M2ohHR2zd3ekD5WLOll.icytUsKAjpzeoeTu3ZaYvpq0aRKW'

USERS = [
    (1, 'admin', '系统管理员', 'admin', 1, False, _DEFAULT_HASH),
    # 对接人
    (10, 'zhongmengxi', '钟梦茜', 'handler', 1, False, _DEFAULT_HASH),
    (11, 'xiezhipeng', '谢志鹏', 'handler', 1, False, _DEFAULT_HASH),
    (12, 'zhangzhaojuan', '张朝娟', 'handler', 1, False, _DEFAULT_HASH),
    (13, 'lianlu', '练露', 'handler', 1, False, _DEFAULT_HASH),
    (14, 'zhanghua', '张华', 'handler', 1, False, _DEFAULT_HASH),
    (15, 'qiuwenwei', '丘文伟', 'handler', 1, False, _DEFAULT_HASH),
    # 处理人
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
USER_SKILL_GROUPS = [
    # 对接人
    (10, 1, True),   # 钟梦茜 -> 品牌公关传播
    (11, 2, True),   # 谢志鹏 -> 市场生态部
    (12, 3, True),   # 张朝娟 -> 产品中心
    (13, 4, True),   # 练露 -> 网运部
    (14, 5, True),   # 张华 -> 售后
    (15, 4, True),   # 丘文伟 -> 网运部
    # 处理人
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

CATEGORIES = [
    # 一级分类 (id, parent_id, name, level, sort_order)
    (1, None, '咨询类', 1, 1),
    (2, None, '业务类', 1, 2),
    (3, None, '故障类', 1, 3),
    (4, None, '投诉类', 1, 4),
    (5, None, '其他', 1, 5),
    # 二级分类：咨询类
    (101, 1, '品牌咨询', 2, 1),
    (102, 1, '渠道/代理规则咨询', 2, 2),
    (103, 1, '资费套餐（定义和类型）', 2, 3),
    (104, 1, '产品&参数咨询', 2, 4),
    (105, 1, '操作使用咨询', 2, 5),
    (106, 1, '其他', 2, 6),
    # 二级分类：业务类
    (201, 2, '渠道/代理合同&合作洽谈', 2, 1),
    (202, 2, '业务办理', 2, 2),
    (203, 2, '发票办理', 2, 3),
    (204, 2, '账单&缴费异议', 2, 4),
    (205, 2, '资费异议', 2, 5),
    (206, 2, '其他', 2, 6),
    # 二级分类：故障类
    (301, 3, '终端硬件故障', 2, 1),
    (302, 3, 'SIM卡故障', 2, 2),
    (303, 3, '外设&配套故障', 2, 3),
    (304, 3, '数据传输故障', 2, 4),
    (305, 3, '网络&星座链路故障', 2, 5),
    (306, 3, '平台故障', 2, 6),
    (307, 3, '其他', 2, 7),
    # 二级分类：投诉类
    (401, 4, '服务态度投诉', 2, 1),
    (402, 4, '服务时效投诉', 2, 2),
    (403, 4, '服务质量', 2, 3),
    (404, 4, '综合意见&建议投诉', 2, 4),
    (405, 4, '群体性&应急投诉', 2, 5),
    (406, 4, '履约投诉', 2, 6),
    (407, 4, '其他', 2, 7),
    # 二级分类：其他
    (501, 5, '其他', 2, 1),
]


async def seed() -> None:
    now = datetime.now(timezone.utc)
    async with async_session() as db:
        # 只在 users 表为空时灌入数据，避免重复执行
        result = await db.execute(select(text("1")).select_from(text("users")).limit(1))
        if result.scalar_one_or_none() is not None:
            print("Seed skipped: users table already populated.")
            return

        print("Seeding regions...")
        await db.execute(
            text("""
                INSERT INTO regions (id, parent_id, name, level, code, sort_order, is_active, created_at, updated_at)
                VALUES (:id, :parent_id, :name, :level, :code, :sort_order, :is_active, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            [
                {
                    "id": r[0], "parent_id": r[1], "name": r[2],
                    "level": r[3], "code": r[4], "sort_order": r[5],
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                }
                for r in REGIONS
            ],
        )

        print("Seeding groups...")
        await db.execute(
            text("""
                INSERT INTO groups (id, name, created_at, updated_at)
                VALUES (:id, :name, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            [
                {
                    "id": g[0], "name": g[1],
                    "created_at": now,
                    "updated_at": now,
                }
                for g in GROUPS
            ],
        )

        print("Seeding skill_groups...")
        await db.execute(
            text("""
                INSERT INTO skill_groups (id, name, created_at, updated_at)
                VALUES (:id, :name, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            [
                {
                    "id": sg[0], "name": sg[1],
                    "created_at": now,
                    "updated_at": now,
                }
                for sg in SKILL_GROUPS
            ],
        )

        print("Seeding users...")
        await db.execute(
            text("""
                INSERT INTO users (id, username, name, role, group_id, is_group_leader, password_hash, is_active, created_at, updated_at)
                VALUES (:id, :username, :name, :role, :group_id, :is_group_leader, :password_hash, :is_active, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            [
                {
                    "id": u[0], "username": u[1], "name": u[2], "role": u[3],
                    "group_id": u[4], "is_group_leader": u[5], "password_hash": u[6],
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                }
                for u in USERS
            ],
        )

        print("Seeding user_skill_groups...")
        await db.execute(
            text("""
                INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher)
                VALUES (:user_id, :skill_group_id, :is_dispatcher)
                ON CONFLICT DO NOTHING
            """),
            [
                {"user_id": usg[0], "skill_group_id": usg[1], "is_dispatcher": usg[2]}
                for usg in USER_SKILL_GROUPS
            ],
        )

        print("Seeding categories...")
        await db.execute(
            text("""
                INSERT INTO ticket_categories (id, parent_id, name, level, sort_order, is_active, created_at, updated_at)
                VALUES (:id, :parent_id, :name, :level, :sort_order, :is_active, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            [
                {
                    "id": c[0], "parent_id": c[1], "name": c[2],
                    "level": c[3], "sort_order": c[4],
                    "is_active": True,
                    "created_at": now,
                    "updated_at": now,
                }
                for c in CATEGORIES
            ],
        )

        # 显式 id 插入后必须重置序列，否则后续自增会冲突
        for table in ["regions", "groups", "skill_groups", "users", "ticket_categories"]:
            await db.execute(
                text(f"""
                    SELECT setval('{table}_id_seq', COALESCE((SELECT MAX(id) FROM {table}), 1))
                """)
            )

        await db.commit()
        print("Seed completed.")


if __name__ == "__main__":
    asyncio.run(seed())
