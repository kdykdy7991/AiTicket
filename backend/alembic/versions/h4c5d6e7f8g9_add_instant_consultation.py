"""Add a new immediate consultation category without restoring deleted 1102 data.

Revision ID: h4c5d6e7f8g9
Revises: g3b4c5d6e7f8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h4c5d6e7f8g9"
down_revision: Union[str, Sequence[str], None] = "g3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        INSERT INTO ticket_categories
            (id, parent_id, name, level, sort_order, is_active, requires_callback, created_at, updated_at)
        VALUES (1205, 1001, '即时办结咨询', 2, 4, true, false, now(), now())
        ON CONFLICT (id) DO NOTHING
    """))


def downgrade() -> None:
    # Preserve the category reference on historical tickets while preventing new intake.
    op.execute(sa.text("""
        UPDATE ticket_categories SET is_active = false, updated_at = now()
        WHERE id = 1205 AND EXISTS (SELECT 1 FROM tickets WHERE category_id = 1205)
    """))
    op.execute(sa.text("""
        DELETE FROM ticket_categories WHERE id = 1205
        AND NOT EXISTS (SELECT 1 FROM tickets WHERE category_id = 1205)
    """))
