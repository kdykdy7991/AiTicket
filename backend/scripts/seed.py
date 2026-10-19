"""Idempotent seed data for fresh deployments.

Run after `alembic upgrade head` to populate default regions and test users.
Safe to run multiple times (uses ON CONFLICT DO NOTHING).
"""

import asyncio
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# `python scripts/seed.py` puts scripts/ on sys.path, not the backend root, so
# `app` and `scripts` are not importable until the backend root is added.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.group import SkillGroup, UserSkillGroup
from app.models.user import User

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
    (1, '客服组'),
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
    (121, '其他组'),
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
    (26, 'wangyaozong', '王耀宗', 'agent', 1, False, _SKDY_HASH),
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
    (30, 121, False),  # 乔永亮 -> 其他组（待确认正式部门）
    (35, 121, False),  # 杨冰 -> 其他组（待确认正式部门）
    (36, 121, False),  # 楼豪丽 -> 其他组（待确认正式部门）
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
                INSERT INTO ticket_categories (id, parent_id, name, level, sort_order, is_active, requires_callback,
                 created_at, updated_at)
                VALUES (:id, :parent_id, :name, :level, :sort_order, :is_active,
                        :requires_callback, :created_at, :updated_at)
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


# ── Phase 9: 分类与正式分派链基础数据 ─────────────
# 服务投诉的重要/重大分支尚无正式链，保留其父级旧 Rule 作为 fallback。

# v2 leaf 分类 ID（与 f2a3b4c5d6e7 同步）
V2_CAT = {
    "服务投诉":        2101,
    "业务运营":        2201,
    "业务保障":        2301,
    "核心网系统":      2311,
    "测运控系统":      2312,
    "卫星系统":        2313,
}

# 要求回访的分类规则（business rule, 不是工单事实）。
# 语义见 app/services/callback_policy.py：标在某个分类上 = 该分类及其全部后代都要求回访。
#   - 业务保障(2301)         一级整体要求回访 → 覆盖其所有后代
#   - 业务运营/套餐变更(2203) 只覆盖该分支
#   - 业务运营/业财对账(2204) 只覆盖该分支
# 业务运营(2201) 本身不标，因此其余业务运营子分类默认无需回访。
CALLBACK_REQUIRED_CATEGORY_IDS = {
    V2_CAT["业务保障"],
    2203,   # 业务运营 / 套餐变更
    2204,   # 业务运营 / 业财对账
}

# 尚需旧 Rule 的服务投诉协调部门；测运控组转由正式链部门表维护。
V2_SKILL_GROUPS = [
    (100, "服务投诉协调组"),         # 服务投诉主对接
]

# v2 用户。用户名 + 密码 hash（用 _SKDY_HASH）
# 角色分两类：
#   - 协调人：is_dispatcher=True
#   - 专业处理人：is_dispatcher=False
V2_USERS = [
    (200, "v2_dispatcher_complaint",  "服务投诉协调人",   "agent", 1, False, _SKDY_HASH),
]

# (user_id, skill_group_id, is_dispatcher)
V2_USER_SKILL_GROUPS = [
    (200, 100, True),  # 服务投诉协调人 -> 服务投诉协调组
]

# (category_id, dispatcher_skill_group_id, dispatcher_id,
#   handler_skill_group_id, owner_id, enabled, note)
# 重要/重大投诉无正式链，仍沿父链回退到服务投诉 Rule。
V2_ROUTING_RULES = [
    (V2_CAT["服务投诉"],     100, 200, None, None, True,
     "服务投诉统一由服务投诉协调组对接；具体专业部门按投诉类别后续补"),
]

# 与 alembic f2a3b4c5d6e7 + m7p9q0r1s2t3 保持一致的 v2 分类树定义（用于 CLI 重灌）。
# 测试环境的 TRUNCATE 会清掉数据但 alembic_version 仍是 head，
# 所以这里在 phase9 重新插一次以保持幂等。
#
# m7p9q0r1s2t3 起不再有「客户服务」中间层：服务投诉/业务运营/业务保障
# 与客户咨询并列为一级分类。
V2_CATEGORIES = [
    (1001, None, "客户咨询", 1, 1),
    (1202, 1001, "品牌合作", 2, 1),
    (1203, 1001, "产品使用/参数咨询", 2, 2),
    (1204, 1001, "渠道/代理合作", 2, 3),
    (2101, None, "服务投诉", 1, 2),
    (2102, 2101, "一般投诉", 2, 1),
    (2103, 2101, "重要投诉", 2, 2),
    (2104, 2101, "重大投诉", 2, 3),
    (2201, None, "业务运营", 1, 3),
    (2203, 2201, "套餐变更", 2, 2),
    (2204, 2201, "业财对账", 2, 3),
    (2301, None, "业务保障", 1, 4),
    (2302, 2301, "应用平台", 2, 1),
    (2310, 2301, "星座大系统", 2, 2),
    (2311, 2310, "核心网系统", 3, 1),
    (2312, 2310, "测运控系统", 3, 2),
    (2313, 2310, "卫星系统", 3, 3),
    (2321, 2301, "终端软件", 2, 3),
    (2322, 2301, "硬件故障", 2, 4),
]


# Phase 9 补丁：组织名称迁移。
#
# 背景：v2 分类树（leaf: 1202/1203/1204）上线时，老的 skill_group
# 仍叫「品牌公关传播」「产品中心」「市场生态部」；业务侧对外的 v2 名称
# 调整为「品牌传播与大客户」「产品」「市场生态部」。名称需要与正式
# dispatch_chain 的 department_code 一致。
#
# 保留现有 id，仅在旧名称匹配时 rename，重复执行幂等。
#
# BUSINES TODO（不动 app 代码）：
#   - 业务侧需最终确认「品牌传播与大客户」「产品」是否为对外最终名
#   - 若要求迁移可独立审计，可改为 alembic 数据迁移（data migration）
V2_LEAF_RENAMES = [
    # (id, 旧名 → 新名)
    (1, "品牌公关传播", "品牌传播与大客户"),
    (3, "产品中心",     "产品"),
    # 2 市场生态部 不变
]

# ── dispatch_chains：分派设计 V0.21（docs/ticket_dispatch_design.md §4）──
# (category_id, [部门代称...], note)
#
# 判断层级（设计 §2）：客服判到 L1（业务保障等）→ 售后判 L2 →
# 星座大系统负责人判 L3。链的起点 = 分类落位后接续的部门；
# 判断节点所在部门写进链里作为下一步（如 2301→售后）。
#
# 不配链的分类（本轮保留原路径）：
#   2103 重要投诉 / 2104 重大投诉 —— 父级旧 Rule 负责路由，
#   complaint_escalation_policies 负责投诉级别策略。
DISPATCH_CHAINS: list[tuple[int, list[str], str]] = [
    (1202, ["品牌传播与大客户"],   "咨询/品牌合作：单步直达"),
    (1203, ["产品"],               "咨询/产品使用/参数咨询：单步直达"),
    (1204, ["市场生态部"],         "咨询/渠道/代理合作：单步直达"),
    (2102, ["值班组"],             "一般投诉：值班组承接（人员按班次维护）"),
    (2203, ["市场生态部", "业务支撑组"], "套餐变更：审核→执行，两步"),
    (2204, ["经营管理部", "财务"],       "业财对账：审核→开票，两步"),
    (2301, ["售后"],               "业务保障：客服判到此级，售后在此分诊（L2 四选一）"),
    (2302, ["平台运维组", "售后"], "应用平台处理后由售后致电反馈"),
    (2310, ["星座大系统负责人"],   "售后分诊到此，负责人在此再判断（L3 三选一）"),
    (2311, ["软件开发组", "售后"], "核心网处理后由售后致电反馈"),
    (2312, ["测运控组", "售后"], "测运控处理后由售后致电反馈"),
    (2313, ["整星产品", "售后"], "卫星系统处理后由售后致电反馈"),
    (2321, ["终端研发", "售后"], "终端软件处理后由售后致电反馈"),
    (2322, ["售后", "售后", "售后"], "硬件故障：售后判断、处理、致电反馈依次办理"),
]

FEEDBACK_CATEGORY_IDS = {2302, 2311, 2312, 2313, 2321, 2322}


def dispatch_chain_steps(category_id: int, departments: list[str]) -> list[dict]:
    steps = []
    for index, department in enumerate(departments):
        step = {"order": index + 1, "department_code": department}
        if category_id in FEEDBACK_CATEGORY_IDS and index == len(departments) - 1:
            step["stage"] = "phone_feedback"
        elif category_id == 2322 and index == 0:
            step["stage"] = "judgement"
        steps.append(step)
    return steps

# ── 分派设计 V0.21 §4 表A/表B 补齐（链部门代称 → skill_groups）──
# DISPATCH_CHAINS 里的部门代称若 skill_groups 不存在，派单引擎按名字查不到部门。
# 已存在复用：品牌传播与大客户(1) 市场生态部(2) 产品(3) 售后(5)。
DISPATCH_DEPT_GROUPS: list[tuple[int, str]] = [
    (104, "测运控组"),             # 正式链使用；不能随旧 v2 处理人删除
    (110, "值班组"),               # §5.1 一般投诉承接，人员按班次维护
    (111, "业务支撑组"),           # 套餐变更第 2 步
    (112, "经营管理部"),           # 业财对账第 1 步
    (113, "财务"),                 # 业财对账第 2 步
    (114, "平台运维组"),           # 业务保障/应用平台
    (115, "星座大系统负责人"),     # §5.3 第 3 级判断人（占位账号）
    (116, "软件开发组"),           # L3/核心网系统
    (117, "整星产品"),             # L3/卫星系统
    (118, "终端研发"),             # 业务保障/终端软件
    (119, "客户服务组"),           # 表B（责任部门文档）
]

# 表B 缺失的人员（新账号，默认密码 skdy123）。
# 已存在复用：钟梦茜(10) 谢志鹏(11) 张朝娟(12) 练露(13) 张华(14)
#             丘文伟(15) 王耀宗(26)。
DISPATCH_EXTRA_USERS: list[tuple[int, str, str]] = [
    (220, "yibo",              "易波"),
    (221, "lichenyang",        "李晨阳"),
    (222, "qiaoliang",         "乔良"),
    (223, "nihanhua",          "倪汉华"),
    (224, "luxiang",           "卢翔"),
    (225, "liyouquan",         "李有全"),
    (226, "constellation_lead", "星座大系统负责人"),  # §5.3 占位账号
]

# 表B 映射（user_id, skill_group_id, is_dispatcher）。
# 设计约定"单人部门 = 对接人即处理人"：链上每个部门都要有人能执行
# pending→open（分派权限按 is_dispatcher 判定），故单人部门一律 True。
DISPATCH_USER_SKILL_GROUPS: list[tuple[int, int, bool]] = [
    # 已有用户 → 链部门（原映射保留，本表只增不删）
    (13, 111, True),   # 练露 → 业务支撑组（表B both；原网运部映射保留）
    (15, 114, True),   # 丘文伟 → 平台运维组
    (26, 119, True),   # 王耀宗 → 客户服务组
    (26, 110, True),   # 王耀宗 → 值班组（默认值班人；班次轮换改 effective 区间）
    # 新账号 → 链部门
    (220, 112, True),  # 易波 → 经营管理部
    (221, 113, True),  # 李晨阳 → 财务
    (222, 116, True),  # 乔良 → 软件开发组
    (223, 104, True),  # 倪汉华 → 测运控组（表B handler；组内唯一对接人）
    (224, 117, True),  # 卢翔 → 整星产品
    (225, 118, True),  # 李有全 → 终端研发
    (226, 115, True),  # 占位账号 → 星座大系统负责人
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
                    "requires_callback": cid in CALLBACK_REQUIRED_CATEGORY_IDS,
                    "created_at": now, "updated_at": now,
                }
                for (cid, parent, name, level, sort) in V2_CATEGORIES
            ],
        )
        # 分类规则可能后补：把标记为要求回访的分类幂等置真，其余置假。
        # 只动规则标记，不触碰存量工单已记录的 tickets.callback_required。
        await db.execute(
            text("""
                UPDATE ticket_categories
                SET requires_callback = (id = ANY(:ids)), updated_at = :now
                WHERE requires_callback IS DISTINCT FROM (id = ANY(:ids))
            """),
            {"ids": sorted(CALLBACK_REQUIRED_CATEGORY_IDS), "now": now},
        )
        # 旧「非即时」仅是容器；三个咨询子类已直接挂到「客户咨询」。
        await db.execute(text("DELETE FROM ticket_categories WHERE id = 1201"))
        print("[Phase 9] Seeding customer service group (id=1)...")
        await db.execute(
            text("""
                INSERT INTO groups (id, name, created_at, updated_at)
                VALUES (1, :name, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            {"name": "客服组", "created_at": now, "updated_at": now},
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

        # ── Phase 9 补丁：组织 rename ──
        # 业务背景：v2 业务侧把「品牌公关传播」→「品牌传播与大客户」、
        # 「产品中心」→「产品」；但旧 id(1/3) 与 dispatcher 绑定
        # (钟梦茜→1、张朝娟→3) 都稳定，沿用 RENAME 路径而不是新建组。
        print("[Phase 9] Renaming legacy skill_groups to v2 names...")
        for sg_id, old_name, new_name in V2_LEAF_RENAMES:
            await db.execute(
                text("""
                    UPDATE skill_groups
                    SET name = :new_name, updated_at = :now
                    WHERE id = :sg_id AND name = :old_name
                """),
                {"sg_id": sg_id, "old_name": old_name, "new_name": new_name, "now": now},
            )

        # ── 分派设计 V0.21 §4 表B：链部门 + 人员补齐（幂等）──
        # 必须先于 dispatch_chains 校验逻辑可用：链的 department_code 按名字
        # 查 skill_groups，缺部门则派单引擎找不到受理人。
        print("[Phase 9] Seeding dispatch dept skill_groups...")
        await db.execute(
            text("""
                INSERT INTO skill_groups (id, name, created_at, updated_at)
                VALUES (:id, :name, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            [
                {"id": gid, "name": name, "created_at": now, "updated_at": now}
                for gid, name in DISPATCH_DEPT_GROUPS
            ],
        )
        # 兜底：id 被占用但名字没建出来时按名字补（冲突仅在历史脏数据时触发）
        for gid, name in DISPATCH_DEPT_GROUPS:
            exists = await db.execute(
                select(SkillGroup.id).where(SkillGroup.name == name).limit(1)
            )
            if not exists.scalar_one_or_none():
                await db.execute(
                    text("""
                        INSERT INTO skill_groups (name, created_at, updated_at)
                        VALUES (:name, :created_at, :updated_at)
                        ON CONFLICT (name) DO NOTHING
                    """),
                    {"name": name, "created_at": now, "updated_at": now},
                )
                print(f"  [warn] id={gid} 被占用，按名字新建部门: {name}")

        print("[Phase 9] Seeding dispatch extra users...")
        await db.execute(
            text("""
                INSERT INTO users (id, username, name, role, group_id, is_group_leader,
                                   password_hash, is_active, created_at, updated_at)
                VALUES (:id, :username, :name, 'handler', 1, false,
                        :password_hash, true, :created_at, :updated_at)
                ON CONFLICT (id) DO NOTHING
            """),
            [
                {"id": uid, "username": uname, "name": name,
                 "password_hash": _SKDY_HASH, "created_at": now, "updated_at": now}
                for uid, uname, name in DISPATCH_EXTRA_USERS
            ],
        )

        print("[Phase 9] Seeding dispatch user_skill_groups (表B)...")
        await db.execute(
            text("""
                INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher)
                VALUES (:user_id, :skill_group_id, :is_dispatcher)
                ON CONFLICT DO NOTHING
            """),
            [
                {"user_id": uid, "skill_group_id": gid, "is_dispatcher": disp}
                for uid, gid, disp in DISPATCH_USER_SKILL_GROUPS
            ],
        )

        # ── 校验：dispatch_chains 的每个 department_code 都要有部门与对接人 ──
        chain_depts = {d for _, depts, _ in DISPATCH_CHAINS for d in depts}
        rows = await db.execute(select(SkillGroup.id, SkillGroup.name))
        sg_by_name = {name: gid for gid, name in rows.all()}
        missing_depts = sorted(chain_depts - set(sg_by_name))
        if missing_depts:
            print(f"  [ERROR] 链部门缺失 skill_groups: {missing_depts}")
        for dept in sorted(chain_depts & set(sg_by_name)):
            disp = await db.execute(
                select(func.count()).select_from(UserSkillGroup).where(
                    UserSkillGroup.skill_group_id == sg_by_name[dept],
                    UserSkillGroup.is_dispatcher == True,  # noqa: E712
                )
            )
            if (disp.scalar() or 0) == 0:
                print(f"  [ERROR] 部门无对接人（无法分派）: {dept}")

        # ── dispatch_chains（分派设计 V0.21 §4，重复执行幂等刷新为权威值）──
        print("[Phase 9] Seeding dispatch_chains...")
        for cat_id, depts, note in DISPATCH_CHAINS:
            steps = dispatch_chain_steps(cat_id, depts)
            await db.execute(
                text("""
                    INSERT INTO dispatch_chains
                    (category_id, steps, enabled, note, created_at, updated_at)
                    VALUES (:cat_id, CAST(:steps AS json), TRUE, :note, :now, :now)
                    ON CONFLICT (category_id) DO UPDATE SET
                        steps = EXCLUDED.steps,
                        enabled = TRUE,
                        note = EXCLUDED.note,
                        updated_at = EXCLUDED.updated_at
                """),
                {
                    "cat_id": cat_id,
                    "steps": json.dumps(steps, ensure_ascii=False),
                    "note": note,
                    "now": now,
                },
            )
            print(f"  [ok] chain {cat_id}: {' → '.join(depts)}")

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
        await db.execute(
            text("""
                SELECT setval('dispatch_chains_id_seq',
                              COALESCE((SELECT MAX(id) FROM dispatch_chains), 1))
            """)
        )

        await db.commit()
        print("[Phase 9] Seed completed.")
    if own_engine:
        await local_engine.dispose()


async def seed_node_forms() -> None:
    """Publish the v1 node forms for triage / processing / phone_feedback.

    Own engine inside a single event loop: sharing this module's session factory
    across separate ``asyncio.run()`` calls binds its engine to the first loop and
    raises "attached to a different loop" on every later one.
    """
    from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

    from scripts.seed_closure_form import seed_closure_form
    from scripts.seed_closure_v4_form import seed_closure_v4_form
    from scripts.seed_phone_feedback_form import seed_phone_feedback_form
    from scripts.seed_processing_form import seed_processing_form
    from scripts.seed_package_change_review_form import seed_package_change_review_form
    from scripts.seed_package_change_execute_form import seed_package_change_execute_form
    from scripts.seed_sales_opportunity_form import seed_sales_opportunity_form
    from scripts.seed_triage_form import seed_triage_form
    from scripts.seed_constellation_triage_form import seed_constellation_triage_form

    local_engine = create_async_engine(DATABASE_URL, future=True)
    factory = async_sessionmaker(local_engine, class_=AsyncSession, expire_on_commit=False)
    try:
        for seed in (seed_triage_form, seed_constellation_triage_form,
                     seed_processing_form, seed_package_change_review_form,
                     seed_package_change_execute_form,
                     seed_phone_feedback_form, seed_closure_form, seed_closure_v4_form,
                     seed_sales_opportunity_form):
            await seed(factory)
    finally:
        await local_engine.dispose()


if __name__ == "__main__":
    asyncio.run(seed())
    if "--phase9" in sys.argv:
        asyncio.run(seed_phase9_base_data())
    asyncio.run(seed_node_forms())
