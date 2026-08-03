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
    (7, '星座营销中心'),
    (8, '星空智联行销部'),
]

# 分类（只确保存在，不删除已有分类；用 id 做 upsert，可覆盖旧分类名）
CATEGORIES = [
    # 一级分类 (id, parent_id, name, level, sort_order)
    (1, None, '咨询类', 1, 1),
    (2, None, '业务类', 1, 2),
    (3, None, '故障类', 1, 3),
    (4, None, '投诉类', 1, 4),
    (5, None, '其他', 1, 5),
    (6, None, '错号', 1, 6),
    (7, None, '广告推销', 1, 7),
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
    (502, 5, '北斗终端', 2, 2),
    (503, 5, '车载', 2, 3),
    (504, 5, '海外业务', 2, 4),
    (505, 5, '卫星业务', 2, 5),
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
    # V0.7 新增对接人
    (26, 'wangyaozong', '王耀宗', 'handler', 1, False, _DEFAULT_HASH),
    (31, 'wangjunhua', '汪军华', 'handler', 1, False, _DEFAULT_HASH),
    (35, 'yangbing', '杨冰', 'handler', 1, False, _DEFAULT_HASH),
    (37, 'caoxin', '曹欣', 'handler', 1, False, _DEFAULT_HASH),
    # V0.7 新增处理人
    (27, 'zhengkaixin', '郑恺心', 'handler', 1, False, _DEFAULT_HASH),
    (28, 'chengwei', '程伟', 'handler', 1, False, _DEFAULT_HASH),
    (29, 'dongming', '董明', 'handler', 1, False, _DEFAULT_HASH),
    (30, 'qiaoyongliang', '乔永亮', 'handler', 1, False, _DEFAULT_HASH),
    (32, 'zhangguanghan', '张广瀚', 'handler', 1, False, _DEFAULT_HASH),
    (33, 'wuxiaohan', '吴小涵', 'handler', 1, False, _DEFAULT_HASH),
    (34, 'qiaoxingda', '乔兴达', 'handler', 1, False, _DEFAULT_HASH),
    (36, 'louhaoli', '楼豪丽', 'handler', 1, False, _DEFAULT_HASH),
]

# (user_id, skill_group_id, is_dispatcher)
HANDLER_SKILL_GROUPS = [
    (17, 1, False),  # 金鑫 -> 品牌公关传播
    (18, 1, False),  # 丁晛 -> 品牌公关传播
    (19, 1, False),  # 张景熙 -> 品牌公关传播
    (27, 1, False),  # 郑恺心 -> 品牌公关传播
    (20, 2, False),  # 徐挺 -> 市场生态部
    (21, 2, False),  # 王颜 -> 市场生态部
    (22, 3, False),  # 蒋超毅 -> 产品中心
    (28, 3, False),  # 程伟 -> 产品中心
    (29, 3, False),  # 董明 -> 产品中心
    (23, 4, False),  # 金军 -> 网运部
    (24, 5, False),  # 姜伟业 -> 售后
    (25, 5, False),  # 陈文兵 -> 售后
    (26, 6, True),   # 王耀宗 -> 客服组（对接人）
    (31, 7, True),   # 汪军华 -> 星座营销中心（对接人）
    (37, 8, True),   # 曹欣 -> 星空智联行销部（对接人）
    (32, 7, False),  # 张广瀚 -> 星座营销中心
    (33, 7, False),  # 吴小涵 -> 星座营销中心
    (34, 7, False),  # 乔兴达 -> 星座营销中心
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

        print("Upserting categories...")
        await db.execute(
            text("""
                INSERT INTO ticket_categories (id, parent_id, name, level, sort_order, is_active, created_at, updated_at)
                VALUES (:id, :parent_id, :name, :level, :sort_order, :is_active, :created_at, :updated_at)
                ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, parent_id = EXCLUDED.parent_id, level = EXCLUDED.level, sort_order = EXCLUDED.sort_order
            """),
            [
                {
                    "id": c[0], "parent_id": c[1], "name": c[2],
                    "level": c[3], "sort_order": c[4],
                    "is_active": True, "created_at": now, "updated_at": now,
                }
                for c in CATEGORIES
            ],
        )
        # 重置 ticket_categories 序列，避免后续插入冲突
        await db.execute(text("SELECT setval('ticket_categories_id_seq', COALESCE((SELECT MAX(id) FROM ticket_categories), 1))"))

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
