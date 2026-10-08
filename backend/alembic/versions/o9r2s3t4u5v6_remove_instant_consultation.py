"""Remove instant consultation category and its recorded tickets.

套餐查询（2202）仍保留即时办结规则。

Revision ID: o9r2s3t4u5v6
Revises: n8q1r2s3t4u5
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "o9r2s3t4u5v6"
down_revision: Union[str, Sequence[str], None] = "n8q1r2s3t4u5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # ticket_state_logs/articles/reminders/notifications 按 FK 级联删除。
    bind.execute(sa.text("DELETE FROM tickets WHERE category_id = 1102"))
    # 路由规则也按 FK 级联删除。
    bind.execute(sa.text("DELETE FROM ticket_categories WHERE id = 1102"))
    bind.execute(sa.text("DELETE FROM ticket_categories WHERE id = 1101"))


def downgrade() -> None:
    # 被删除的工单不能由迁移重建；仅恢复旧分类结构供回滚使用。
    bind = op.get_bind()
    bind.execute(sa.text("""
        INSERT INTO ticket_categories
            (id, parent_id, name, level, sort_order, is_active, created_at, updated_at)
        VALUES (1101, 1001, '即时', 2, 1, false, now(), now())
        ON CONFLICT (id) DO NOTHING
    """))
    bind.execute(sa.text("""
        INSERT INTO ticket_categories
            (id, parent_id, name, level, sort_order, is_active, created_at, updated_at)
        VALUES (1102, 1101, '即时办结咨询', 3, 1, false, now(), now())
        ON CONFLICT (id) DO NOTHING
    """))
