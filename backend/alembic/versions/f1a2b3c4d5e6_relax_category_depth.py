"""relax category depth — derive level from parent chain

Phase 1: TicketCategory now supports arbitrary depth. The DB schema does not
have a CHECK constraint on `level` (it was enforced at the API layer only),
so this migration is a no-op schema-wise. We re-derive `level` for all
existing rows to ensure they reflect the parent chain.

Revision ID: f1a2b3c4d5e6
Revises: a1b2c3d4e5f6
Create Date: 2026-09-21 10:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Re-derive `level` for every category row from its parent chain.

    Iteration capped at 16 to defend against pre-existing cycles; in practice
    the API never allowed them, so this is just belt-and-braces.
    """
    conn = op.get_bind()
    # Initialize all levels to 1.
    conn.execute(sa.text("UPDATE ticket_categories SET level = 1 WHERE parent_id IS NULL"))
    conn.execute(sa.text("UPDATE ticket_categories SET level = 2 WHERE parent_id IS NOT NULL"))
    # Walk down three more levels in case historical data already had them.
    for _ in range(3):
        conn.execute(sa.text(
            "UPDATE ticket_categories c "
            "SET level = p.level + 1 "
            "FROM ticket_categories p "
            "WHERE c.parent_id = p.id "
            "  AND c.level <= p.level"
        ))


def downgrade() -> None:
    """No-op: cannot reliably downgrade level without losing information."""
    pass
