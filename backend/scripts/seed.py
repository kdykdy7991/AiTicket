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
    (7, '星座营销中心'),
    (8, '星空智联行销部'),
]

# 默认密码：admin 为 admin123，其余为 skdy123
_ADMIN_HASH = '$2b$12$Oxx10M2ohHR2zd3ekD5WLOll.icytUsKAjpzeoeTu3ZaYvpq0aRKW'
_SKDY_HASH = '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O'

USERS = [
    (1, 'admin', '系统管理员', 'admin', 1, False, _ADMIN_HASH),
    # 对接人
    (10, 'zhongmengxi', '钟梦茜', 'handler', 1, False, _SKDY_HASH),
    (11, 'xiezhipeng', '谢志鹏', 'handler', 1, False, _SKDY_HASH),
    (12, 'zhangzhaojuan', '张朝娟', 'handler', 1, False, _SKDY_HASH),
    (13, 'lianlu', '练露', 'handler', 1, False, _SKDY_HASH),
    (14, 'zhanghua', '张华', 'handler', 1, False, _SKDY_HASH),
    (15, 'qiuwenwei', '丘文伟', 'handler', 1, False, _SKDY_HASH),
    # 处理人
    (17, 'jinxin', '金鑫', 'handler', 1, False, _SKDY_HASH),
    (18, 'dingxian', '丁晛', 'handler', 1, False, _SKDY_HASH),
    (19, 'zhangjingxi', '张景熙', 'handler', 1, False, _SKDY_HASH),
    (20, 'xuting', '徐挺', 'handler', 1, False, _SKDY_HASH),
    (21, 'wangyan', '王颜', 'handler', 1, False, _SKDY_HASH),
    (22, 'jiangchaoyi', '蒋超毅', 'handler', 1, False, _SKDY_HASH),
    (23, 'jinjun', '金军', 'handler', 1, False, _SKDY_HASH),
    (24, 'jiangweiye', '姜伟业', 'handler', 1, False, _SKDY_HASH),
    (25, 'chenwenbing', '陈文兵', 'handler', 1, False, _SKDY_HASH),
    # 对接人（V0.7 新增）
    (26, 'wangyaozong', '王耀宗', 'handler', 1, False, _SKDY_HASH),
    (31, 'wangjunhua', '汪军华', 'handler', 1, False, _SKDY_HASH),
    (35, 'yangbing', '杨冰', 'handler', 1, False, _SKDY_HASH),
    (37, 'caoxin', '曹欣', 'handler', 1, False, _SKDY_HASH),
    # 处理人（V0.7 新增）
    (27, 'zhengkaixin', '郑恺心', 'handler', 1, False, _SKDY_HASH),
    (28, 'chengwei', '程伟', 'handler', 1, False, _SKDY_HASH),
    (29, 'dongming', '董明', 'handler', 1, False, _SKDY_HASH),
    (30, 'qiaoyongliang', '乔永亮', 'handler', 1, False, _SKDY_HASH),
    (32, 'zhangguanghan', '张广瀚', 'handler', 1, False, _SKDY_HASH),
    (33, 'wuxiaohan', '吴小涵', 'handler', 1, False, _SKDY_HASH),
    (34, 'qiaoxingda', '乔兴达', 'handler', 1, False, _SKDY_HASH),
    (36, 'louhaoli', '楼豪丽', 'handler', 1, False, _SKDY_HASH),
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
    (26, 6, True),   # 王耀宗 -> 客服组
    (31, 7, True),   # 汪军华 -> 星座营销中心
    (37, 8, True),   # 曹欣 -> 星空智联行销部
    # 处理人
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
    (32, 7, False),  # 张广瀚 -> 星座营销中心
    (33, 7, False),  # 吴小涵 -> 星座营销中心
    (34, 7, False),  # 乔兴达 -> 星座营销中心
]

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


# ── Phase 9: v2 分类与责任体系配套基础数据 ─────────────
# 这部分数据是独立的、可重复执行的，用于在新分类树（Phase 2）下建立
# "协调部门 / 专业部门 / 协调人 / 专业处理人" 的组织结构。
#
# 设计：
# - 每个 v2 leaf 分类挂一条 CategoryRoutingRule
# - 协调部门（dispatcher_skill_group_id）+ 协调人（dispatcher_id）必填
# - 专业处理部门（handler_skill_group_id）+ 专业处理人（owner_id）可选
#   （硬件故障/业务保障 等暂未到位的场景允许只有协调部分）

# v2 leaf 分类 ID（与 f2a3b4c5d6e7 同步）
V2_CAT = {
    "即时办结咨询":     1102,
    "服务投诉":        2101,
    "业务运营":        2201,
    "业务保障":        2301,
    "核心网系统":      2311,
    "测运控系统":      2312,
    "卫星系统":        2313,
}

# 新增的协调 / 专业部门（v2 组织架构）
# 与现有 SKILL_GROUPS 通过 id 区分；为避免冲突，从 100 起。
V2_SKILL_GROUPS = [
    (100, "服务投诉协调组"),         # 服务投诉主对接
    (101, "业务运营组"),             # 业务运营主专业组
    (102, "业务保障组"),             # 业务保障主专业组
    (103, "核心网组"),               # 核心网系统
    (104, "测运控组"),               # 测运控系统
    (105, "卫星组"),                 # 卫星系统
    (106, "即时办结咨询组"),         # 即时办结咨询默认协调
]

# v2 用户。用户名 + 密码 hash（用 _SKDY_HASH）
# 角色分两类：
#   - 协调人：is_dispatcher=True
#   - 专业处理人：is_dispatcher=False
V2_USERS = [
    # 协调人
    (200, "v2_dispatcher_complaint",  "服务投诉协调人",   "agent", 1, False, _SKDY_HASH),
    (201, "v2_dispatcher_ops",         "业务运营协调人",   "agent", 1, False, _SKDY_HASH),
    (202, "v2_dispatcher_assurance",   "业务保障协调人",   "agent", 1, False, _SKDY_HASH),
    (203, "v2_dispatcher_instant",     "即时办结协调人",   "agent", 1, False, _SKDY_HASH),
    # 专业处理人
    (210, "v2_owner_ops",              "业务运营处理人",   "handler", 1, False, _SKDY_HASH),
    (211, "v2_owner_assurance",        "业务保障处理人",   "handler", 1, False, _SKDY_HASH),
    (212, "v2_owner_core",             "核心网处理人",     "handler", 1, False, _SKDY_HASH),
    (213, "v2_owner_tt",               "测运控处理人",     "handler", 1, False, _SKDY_HASH),
    (214, "v2_owner_satellite",        "卫星处理人",       "handler", 1, False, _SKDY_HASH),
]

# (user_id, skill_group_id, is_dispatcher)
V2_USER_SKILL_GROUPS = [
    # 协调人
    (200, 100, True),  # 服务投诉协调人 -> 服务投诉协调组
    (201, 101, True),  # 业务运营协调人 -> 业务运营组
    (202, 102, True),  # 业务保障协调人 -> 业务保障组
    (203, 106, True),  # 即时办结协调人 -> 即时办结咨询组
    # 专业处理人
    (210, 101, False),
    (211, 102, False),
    (212, 103, False),
    (213, 104, False),
    (214, 105, False),
]

# (category_id, dispatcher_skill_group_id, dispatcher_id,
#   handler_skill_group_id, owner_id, enabled, note)
# resolve_rule() 会向上走父链，所以不需要给每个 leaf 都挂规则；
# 这里给业务类别（level 2/3）挂规则即可覆盖其所有子孙。
V2_ROUTING_RULES = [
    (V2_CAT["即时办结咨询"], 106, 203, 106, None, True,
     "即时办结咨询走 archived 流程；协调人=即时办结协调组"),
    (V2_CAT["服务投诉"],     100, 200, None, None, True,
     "服务投诉统一由服务投诉协调组对接；具体专业部门按投诉类别后续补"),
    (V2_CAT["业务运营"],     101, 201, 101, 210, True,
     "业务运营工单由业务运营组闭环"),
    (V2_CAT["业务保障"],     102, 202, 102, 211, True,
     "业务保障工单由业务保障组对接并处理"),
    (V2_CAT["核心网系统"],   102, 202, 103, 212, True,
     "核心网组专业处理；协调人=业务保障组"),
    (V2_CAT["测运控系统"],   102, 202, 104, 213, True,
     "测运控组专业处理；协调人=业务保障组"),
    (V2_CAT["卫星系统"],     102, 202, 105, 214, True,
     "卫星组专业处理；协调人=业务保障组"),
]

# 与 alembic f2a3b4c5d6e7 保持一致的 v2 分类树定义（用于 CLI 重灌）。
# 测试环境的 TRUNCATE 会清掉数据但 alembic_version 仍是 head，
# 所以这里在 phase9 重新插一次以保持幂等。
V2_CATEGORIES = [
    (1001, None, "咨询", 1, 1),
    (1002, None, "客户服务", 1, 2),
    (1101, 1001, "即时", 2, 1),
    (1102, 1101, "即时办结咨询", 3, 1),
    (1201, 1001, "非即时", 2, 1),
    (1202, 1201, "品牌合作", 3, 1),
    (1203, 1201, "产品使用/参数咨询", 3, 2),
    (1204, 1201, "渠道/代理合作", 3, 3),
    (2101, 1002, "服务投诉", 2, 1),
    (2102, 2101, "一般投诉", 3, 1),
    (2103, 2101, "重要投诉", 3, 2),
    (2104, 2101, "重大投诉", 3, 3),
    (2201, 1002, "业务运营", 2, 1),
    (2202, 2201, "套餐查询", 3, 1),
    (2203, 2201, "套餐变更", 3, 2),
    (2204, 2201, "业财对账", 3, 3),
    (2301, 1002, "业务保障", 2, 1),
    (2302, 2301, "应用平台", 3, 1),
    (2310, 2301, "星座大系统", 3, 2),
    (2311, 2310, "核心网系统", 4, 1),
    (2312, 2310, "测运控系统", 4, 2),
    (2313, 2310, "卫星系统", 4, 3),
    (2321, 2301, "终端软件", 3, 3),
    (2322, 2301, "硬件故障", 3, 4),
]


async def seed_phase9_base_data(session_factory: async_sessionmaker | None = None) -> None:
    """Phase 9: 给 v2 分类树播种配套组织架构（重复执行幂等）。

    与 seed() 独立：seed() 灌入老分类的基础数据，seed_phase9_base_data()
    给 v2 分类补 skill_groups / users / category_routing_rules。

    参数 session_factory 用于测试时复用同一连接池；CLI 场景不传则用
    临时新建的引擎，避免 module-level 引擎绑死旧事件循环后无法在新
    loop 里复用的问题。
    """
    own_engine = False
    if session_factory is None:
        local_engine = create_async_engine(DATABASE_URL, future=True)
        session_factory = async_sessionmaker(local_engine, class_=AsyncSession, expire_on_commit=False)
        own_engine = True
    now = datetime.now(timezone.utc)
    async with session_factory() as db:
        # 确保 v2 分类树存在（测试环境 TRUNCATE 后 alembic 不会再跑迁移）
        print("[Phase 9] Ensuring v2 categories...")
        await db.execute(
            text("""
                INSERT INTO ticket_categories
                (id, parent_id, name, level, sort_order, is_active, created_at, updated_at)
                VALUES (:id, :parent_id, :name, :level, :sort_order, :is_active, :created_at, :updated_at)
                ON CONFLICT (id) DO UPDATE SET
                    parent_id = EXCLUDED.parent_id,
                    name = EXCLUDED.name,
                    sort_order = EXCLUDED.sort_order,
                    is_active = EXCLUDED.is_active,
                    updated_at = EXCLUDED.updated_at
            """),
            [
                {
                    "id": cid, "parent_id": parent, "name": name,
                    "level": level, "sort_order": sort, "is_active": True,
                    "created_at": now, "updated_at": now,
                }
                for (cid, parent, name, level, sort) in V2_CATEGORIES
            ],
        )
        print("[Phase 9] Seeding default group (id=1)...")
        await db.execute(
            text("""
                INSERT INTO groups (id, name, created_at, updated_at)
                VALUES (1, :name, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            {"name": "默认组", "created_at": now, "updated_at": now},
        )

        print("[Phase 9] Seeding v2 skill_groups...")
        await db.execute(
            text("""
                INSERT INTO skill_groups (id, name, created_at, updated_at)
                VALUES (:id, :name, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            [
                {"id": sg[0], "name": sg[1],
                 "created_at": now, "updated_at": now}
                for sg in V2_SKILL_GROUPS
            ],
        )

        print("[Phase 9] Seeding v2 users...")
        await db.execute(
            text("""
                INSERT INTO users (id, username, name, role, group_id, is_group_leader,
                                   password_hash, is_active, created_at, updated_at)
                VALUES (:id, :username, :name, :role, :group_id, :is_group_leader,
                        :password_hash, :is_active, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            [
                {
                    "id": u[0], "username": u[1], "name": u[2], "role": u[3],
                    "group_id": u[4], "is_group_leader": u[5],
                    "password_hash": u[6], "is_active": True,
                    "created_at": now, "updated_at": now,
                }
                for u in V2_USERS
            ],
        )

        print("[Phase 9] Seeding v2 user_skill_groups...")
        await db.execute(
            text("""
                INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher)
                VALUES (:user_id, :skill_group_id, :is_dispatcher)
                ON CONFLICT DO NOTHING
            """),
            [
                {"user_id": usg[0], "skill_group_id": usg[1], "is_dispatcher": usg[2]}
                for usg in V2_USER_SKILL_GROUPS
            ],
        )

        print("[Phase 9] Seeding v2 category_routing_rules...")
        for rule in V2_ROUTING_RULES:
            cat_id, d_sg, d_uid, h_sg, o_uid, enabled, note = rule
            await db.execute(
                text("""
                    INSERT INTO category_routing_rules
                    (category_id, dispatcher_skill_group_id, dispatcher_id,
                     handler_skill_group_id, owner_id, enabled, note, created_at, updated_at)
                    VALUES (:cat_id, :d_sg, :d_uid, :h_sg, :o_uid, :enabled, :note, :now, :now)
                    ON CONFLICT (category_id) DO NOTHING
                """),
                {
                    "cat_id": cat_id, "d_sg": d_sg, "d_uid": d_uid,
                    "h_sg": h_sg, "o_uid": o_uid,
                    "enabled": enabled, "note": note, "now": now,
                },
            )

        # 重置序列
        await db.execute(
            text("""
                SELECT setval('skill_groups_id_seq',
                              COALESCE((SELECT MAX(id) FROM skill_groups), 1))
            """)
        )
        await db.execute(
            text("""
                SELECT setval('users_id_seq',
                              COALESCE((SELECT MAX(id) FROM users), 1))
            """)
        )
        await db.execute(
            text("""
                SELECT setval('category_routing_rules_id_seq',
                              COALESCE((SELECT MAX(id) FROM category_routing_rules), 1))
            """)
        )

        await db.commit()
        print("[Phase 9] Seed completed.")
    if own_engine:
        await local_engine.dispose()


if __name__ == "__main__":
    import sys
    asyncio.run(seed())
    if "--phase9" in sys.argv:
        asyncio.run(seed_phase9_base_data())
