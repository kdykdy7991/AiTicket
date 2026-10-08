"""Simplify customer consultation to three direct choices.

Historical tickets keep their reference to inactive category 1102.

Revision ID: n8q1r2s3t4u5
Revises: m7p9q0r1s2t3
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "n8q1r2s3t4u5"
down_revision: Union[str, Sequence[str], None] = "m7p9q0r1s2t3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        UPDATE ticket_categories
        SET parent_id = 1001, level = 2, updated_at = now()
        WHERE id IN (1202, 1203, 1204)
    """))
    bind.execute(sa.text("DELETE FROM ticket_categories WHERE id = 1201"))
    bind.execute(sa.text("""
        UPDATE ticket_categories
        SET is_active = false, updated_at = now()
        WHERE id IN (1101, 1102)
    """))


def downgrade() -> None:
    bind = op.get_bind()
    bind.execute(sa.text("""
        INSERT INTO ticket_categories
            (id, parent_id, name, level, sort_order, is_active, created_at, updated_at)
        VALUES (1201, 1001, '非即时', 2, 1, true, now(), now())
        ON CONFLICT (id) DO UPDATE SET is_active = true
    """))
    bind.execute(sa.text("""
        UPDATE ticket_categories
        SET parent_id = 1201, level = 3, updated_at = now()
        WHERE id IN (1202, 1203, 1204)
    """))
    bind.execute(sa.text("""
        UPDATE ticket_categories
        SET is_active = true, updated_at = now()
        WHERE id IN (1101, 1102)
    """))
