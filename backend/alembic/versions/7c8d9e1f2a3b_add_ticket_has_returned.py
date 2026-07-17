"""add ticket has_returned

Revision ID: 7c8d9e1f2a3b
Revises: 6b7c8d9e1a2f
Create Date: 2026-07-06 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c8d9e1f2a3b'
down_revision: Union[str, Sequence[str], None] = '6b7c8d9e1a2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tickets',
        sa.Column('has_returned', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    # 回溯：经历过退回且尚未重新处理的工单打上标记
    # 当前在 returned 状态，或经历过退回流转但之后未再 resolved
    op.execute(
        "UPDATE tickets SET has_returned = true WHERE ("
        "  state = 'returned' OR "
        "  EXISTS ("
        "    SELECT 1 FROM ticket_state_logs log1 "
        "    WHERE log1.ticket_id = tickets.id "
        "    AND ("
        "      log1.to_state = 'returned' OR "
        "      (log1.from_state = 'open' AND log1.to_state = 'pending') OR "
        "      (log1.from_state = 'resolved' AND log1.to_state IN ('open', 'on_hold'))"
        "    ) "
        "    AND NOT EXISTS ("
        "      SELECT 1 FROM ticket_state_logs log2 "
        "      WHERE log2.ticket_id = tickets.id "
        "      AND log2.to_state = 'resolved' "
        "      AND log2.created_at > log1.created_at"
        "    )"
        "  )"
        ")"
    )


def downgrade() -> None:
    op.drop_column('tickets', 'has_returned')
