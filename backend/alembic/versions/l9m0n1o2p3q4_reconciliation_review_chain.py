"""Route new reconciliation tickets through management review and finance.

Revision ID: l9m0n1o2p3q4
Revises: k8l9m0n1o2p3
"""
from alembic import op
import sqlalchemy as sa

revision = "l9m0n1o2p3q4"
down_revision = "k8l9m0n1o2p3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("""
        INSERT INTO dispatch_chains (category_id, steps, enabled, note, created_at, updated_at)
        SELECT 2204, CAST(:steps AS json), true, '业财对账：经管审核→财务处理', now(), now()
        WHERE EXISTS (SELECT 1 FROM ticket_categories WHERE id = 2204)
        ON CONFLICT (category_id) DO UPDATE SET steps = EXCLUDED.steps,
            enabled = true, note = EXCLUDED.note, updated_at = now()
    """), {"steps": '[{"order":1,"department_code":"经营管理部"},{"order":2,"department_code":"财务"}]'})


def downgrade() -> None:
    op.get_bind().execute(sa.text("""
        UPDATE dispatch_chains SET steps = CAST(:steps AS json),
            note = '业财对账：客服指定销售→销售指定财务', updated_at = now()
        WHERE category_id = 2204
    """), {"steps": '[{"order":1,"department_code":"销售"},{"order":2,"department_code":"财务"}]'})
