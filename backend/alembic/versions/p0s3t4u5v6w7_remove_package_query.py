"""Remove the immediate package query category and its tickets.

Revision ID: p0s3t4u5v6w7
Revises: o9r2s3t4u5v6
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "p0s3t4u5v6w7"
down_revision: Union[str, Sequence[str], None] = "o9r2s3t4u5v6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("DELETE FROM tickets WHERE category_id = 2202"))
    bind.execute(sa.text("DELETE FROM ticket_categories WHERE id = 2202"))


def downgrade() -> None:
    op.get_bind().execute(sa.text("""
        INSERT INTO ticket_categories
            (id, parent_id, name, level, sort_order, is_active, created_at, updated_at)
        VALUES (2202, 2201, '套餐查询', 2, 1, false, now(), now())
        ON CONFLICT (id) DO NOTHING
    """))
