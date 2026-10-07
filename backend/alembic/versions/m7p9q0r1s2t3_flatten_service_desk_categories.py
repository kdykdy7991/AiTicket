"""flatten service-desk: promote 服务投诉/业务运营/业务保障 to L1, drop 客户服务

业务口径调整：一级分类不再有「客户服务」这层，中间层去掉，它下面的三个
分类与服务侧的「客户咨询」并列为一级分类：

    客户服务(1002)           ┐
    ├─ 服务投诉(2101)        │
    ├─ 业务运营(2201)   ──────┼─→ 四个平级一级分类
    └─ 业务保障(2301)        ┘
    客户咨询(1001)  ─────────┘

调整后：

    客户咨询(1001)
      ├─ 即时(1101) → 即时办结咨询(1102)
      └─ 非即时(1201) → 品牌合作/产品使用/渠道代理
    服务投诉(2101) → 一般/重要/重大投诉
    业务运营(2201) → 套餐查询/套餐变更/业财对账
    业务保障(2301) → 应用平台/星座大系统(→核心网/测运控/卫星)/终端软件/硬件故障

注意：
- 只动分类树的父子关系，不动任何工单/分派链/路由规则——1002 本身无工单引用
  （category_id 指向叶子分类），其子节点提级后parent 链自洽。
- `level` 列是派生属性（历史遗留，CHECK 约束已删除），这里用递归 CTE 重算，
  保证与 parent 链一致。
- 责任槽位（问题判断组 / 问题处理部门）由 parent 链 + dispatch_chains 推导，
  提级后结论不变：业务保障仍是判断节点（售后判断），核心网系统仍是叶子
  （处理部门=软件开发组，判断组=[售后, 星座大系统负责人]）。

Revision ID: m7p9q0r1s2t3
Revises: l6o8p9q0r1s2
Create Date: 2026-10-07 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "m7p9q0r1s2t3"
down_revision: Union[str, Sequence[str], None] = "l6o8p9q0r1s2"
branch_labels = None
depends_on = None

# 服务投诉/业务运营/业务保障：从「客户服务」下提到一级
PROMOTE_TO_L1 = (2101, 2201, 2301)
# 中间层「客户服务」
DROP_L1 = 1002


def upgrade() -> None:
    bind = op.get_bind()

    # 1) 三个分类提为一级
    bind.execute(
        sa.text(
            "UPDATE ticket_categories SET parent_id = NULL, level = 1 "
            "WHERE id = ANY(:ids)"
        ),
        {"ids": list(PROMOTE_TO_L1)},
    )

    # 2) 删除中间层「客户服务」（已无子节点、无工单引用）
    bind.execute(
        sa.text("DELETE FROM ticket_categories WHERE id = :id"), {"id": DROP_L1}
    )

    # 3) 按 parent 链重算 level（派生属性，与 common._recompute_descendant_levels 同源）
    bind.execute(sa.text("""
        WITH RECURSIVE chain AS (
            SELECT id, 1 AS lvl
            FROM ticket_categories
            WHERE parent_id IS NULL
            UNION ALL
            SELECT c.id, ch.lvl + 1
            FROM ticket_categories c
            JOIN chain ch ON c.parent_id = ch.id
        )
        UPDATE ticket_categories t
        SET level = chain.lvl
        FROM chain
        WHERE t.id = chain.id
    """))


def downgrade() -> None:
    bind = op.get_bind()

    # 复原：重建「客户服务」并把三个分类挂回去
    bind.execute(sa.text("""
        INSERT INTO ticket_categories (id, parent_id, name, level, sort_order, is_active)
        VALUES (:id, NULL, :name, 1, 2, TRUE)
        ON CONFLICT (id) DO UPDATE SET name = EXCLUDED.name, is_active = TRUE
    """), {"id": DROP_L1, "name": "客户服务"})

    bind.execute(
        sa.text(
            "UPDATE ticket_categories SET parent_id = :parent, level = 2 "
            "WHERE id = ANY(:ids)"
        ),
        {"parent": DROP_L1, "ids": list(PROMOTE_TO_L1)},
    )

    bind.execute(sa.text("""
        WITH RECURSIVE chain AS (
            SELECT id, 1 AS lvl
            FROM ticket_categories
            WHERE parent_id IS NULL
            UNION ALL
            SELECT c.id, ch.lvl + 1
            FROM ticket_categories c
            JOIN chain ch ON c.parent_id = ch.id
        )
        UPDATE ticket_categories t
        SET level = chain.lvl
        FROM chain
        WHERE t.id = chain.id
    """))
