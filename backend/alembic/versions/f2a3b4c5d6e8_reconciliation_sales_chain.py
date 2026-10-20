"""Route future reconciliation tickets through sales and finance.

Revision ID: f2a3b4c5d6e8
Revises: e1f2a3b4c5d6
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e8"
down_revision: Union[str, Sequence[str], None] = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("""
        INSERT INTO dispatch_chains (category_id, steps, enabled, note, created_at, updated_at)
        SELECT 2204, CAST(:steps AS json), true,
               '业财对账：客服指定销售→销售指定财务', now(), now()
        WHERE EXISTS (SELECT 1 FROM ticket_categories WHERE id = 2204)
        ON CONFLICT (category_id) DO UPDATE SET
            steps = EXCLUDED.steps, enabled = true,
            note = EXCLUDED.note, updated_at = now()
    """), {"steps": '[{"order":1,"department_code":"销售"},{"order":2,"department_code":"财务"}]'})


def downgrade() -> None:
    op.get_bind().execute(sa.text("""
        UPDATE dispatch_chains
        SET steps = CAST(:steps AS json),
            note = '业财对账：审核→开票，两步', updated_at = now()
        WHERE category_id = 2204
    """), {"steps": '[{"order":1,"department_code":"经营管理部"},{"order":2,"department_code":"财务"}]'})
