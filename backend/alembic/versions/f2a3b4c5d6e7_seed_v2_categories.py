"""seed v2 category tree and retire old top-level categories

Phase 2 of the responsibility/flow overhaul.

- Insert the new category tree (idempotent via ON CONFLICT) covering:
    咨询 / 即时 / 即时办结咨询
    咨询 / 非即时 / 品牌合作 | 产品使用/参数咨询 | 渠道/代理合作
    客户服务 / 服务投诉 / 一般投诉 | 重要投诉 | 重大投诉
    客户服务 / 业务运营 / 套餐查询 | 套餐变更 | 业财对账
    客户服务 / 业务保障 / 应用平台 | 星座大系统 / 核心网系统 | 测运控系统 | 卫星系统
    客户服务 / 业务保障 / 终端软件 | 硬件故障

- Mark the old top-level categories as inactive so the new-ticket picker
  shows only the v2 tree, while historical tickets (which reference these
  categories by id) continue to display correctly via include_inactive=true.

New IDs use 1000+ offset to avoid colliding with the existing 1..505 range.
Existing tickets are NOT modified.

Revision ID: f2a3b4c5d6e7
Revises: f1a2b3c4d5e6
Create Date: 2026-09-21 11:00:00.000000
"""
from typing import Sequence, Union
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: Union[str, Sequence[str], None] = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


# (id, parent_id, name, level, sort_order)
# level 为迁移当时的派生值；运行后会由上一迁移的 level 重算覆盖。
V2_CATEGORIES: list[tuple[int, int | None, str, int, int]] = [
    # ── 一级 ──────────────────────────────────────────────────
    (1001, None, "客户咨询", 1, 1),
    (1002, None, "客户服务", 1, 2),

    # ── 客户咨询 / 即时 ───────────────────────────────────────
    (1101, 1001, "即时", 2, 1),
    (1102, 1101, "即时办结咨询", 3, 1),

    # ── 客户咨询 / 非即时 ────────────────────────────────────
    (1201, 1001, "非即时", 2, 1),
    (1202, 1201, "品牌合作", 3, 1),
    (1203, 1201, "产品使用/参数咨询", 3, 2),
    (1204, 1201, "渠道/代理合作", 3, 3),

    # ── 客户服务 / 服务投诉 ────────────────────────────────────
    (2101, 1002, "服务投诉", 2, 1),
    (2102, 2101, "一般投诉", 3, 1),
    (2103, 2101, "重要投诉", 3, 2),
    (2104, 2101, "重大投诉", 3, 3),

    # ── 客户服务 / 业务运营 ────────────────────────────────────
    (2201, 1002, "业务运营", 2, 1),
    (2202, 2201, "套餐查询", 3, 1),
    (2203, 2201, "套餐变更", 3, 2),
    (2204, 2201, "业财对账", 3, 3),

    # ── 客户服务 / 业务保障 / 应用平台 ─────────────────────────
    (2301, 1002, "业务保障", 2, 1),
    (2302, 2301, "应用平台", 3, 1),

    # ── 客户服务 / 业务保障 / 星座大系统 ──────────────────────
    (2310, 2301, "星座大系统", 3, 2),
    (2311, 2310, "核心网系统", 4, 1),
    (2312, 2310, "测运控系统", 4, 2),
    (2313, 2310, "卫星系统", 4, 3),

    # ── 客户服务 / 业务保障 / 终端软件 + 硬件故障 ─────────────
    (2321, 2301, "终端软件", 3, 3),
    (2322, 2301, "硬件故障", 3, 4),
]


# 旧一级分类 id（seed.py 中的 1..4）：标记为 inactive
OLD_L1_TO_DEACTIVATE = [1, 2, 3, 4]  # 咨询类 / 业务类 / 故障类 / 投诉类


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(timezone.utc)

    # 1) 插入 v2 分类树（幂等：同 id 重复执行覆盖 name/parent/sort/active，level 在第 3 步重算）
    insert_rows = [
        {
            "id": cid,
            "parent_id": parent,
            "name": name,
            "level": level,
            "sort_order": sort,
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        for (cid, parent, name, level, sort) in V2_CATEGORIES
    ]
    if insert_rows:
        bind.execute(sa.text(
            """
            INSERT INTO ticket_categories (id, parent_id, name, level, sort_order, is_active, created_at, updated_at)
            VALUES (:id, :parent_id, :name, :level, :sort_order, :is_active, :created_at, :updated_at)
            ON CONFLICT (id) DO UPDATE SET
                parent_id = EXCLUDED.parent_id,
                name = EXCLUDED.name,
                sort_order = EXCLUDED.sort_order,
                is_active = EXCLUDED.is_active,
                updated_at = EXCLUDED.updated_at
            """
        ), insert_rows)

    # 2) 标记旧一级分类为 inactive（历史工单的 category_id 仍指向旧 id，但前端默认 picker 不再展示）
    if OLD_L1_TO_DEACTIVATE:
        bind.execute(
            sa.text("UPDATE ticket_categories SET is_active = false WHERE id = ANY(:ids)"),
            {"ids": OLD_L1_TO_DEACTIVATE},
        )

    # 3) 统一重算 level（与上一迁移相同的逻辑）
    bind.execute(sa.text("UPDATE ticket_categories SET level = 1 WHERE parent_id IS NULL"))
    for _ in range(8):
        bind.execute(sa.text(
            "UPDATE ticket_categories c SET level = p.level + 1 "
            "FROM ticket_categories p "
            "WHERE c.parent_id = p.id AND c.level <= p.level"
        ))


def downgrade() -> None:
    """Reverse: delete v2 categories (any with id >= 1000) and reactivate old L1.

    Historical tickets pointing at v2 ids will then lose their category
    relationship (FK is ON DELETE SET NULL). This is intentional — downgrades
    should be rare and explicit.
    """
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM ticket_categories WHERE id >= 1000"))
    bind.execute(
        sa.text("UPDATE ticket_categories SET is_active = true WHERE id = ANY(:ids)"),
        {"ids": OLD_L1_TO_DEACTIVATE},
    )
