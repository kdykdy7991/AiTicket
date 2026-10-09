"""Backfill the persistent 'ever returned' marker from flow history.

Revision ID: q1t4u5v6w7x8
Revises: p0s3t4u5v6w7
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "q1t4u5v6w7x8"
down_revision: Union[str, Sequence[str], None] = "p0s3t4u5v6w7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE tickets AS ticket
        SET has_returned = true
        WHERE EXISTS (
            SELECT 1 FROM ticket_state_logs AS log
            WHERE log.ticket_id = ticket.id
              AND (
                  log.action_type IN ('return', 'reopen')
                  OR (log.action_type IS NULL AND (
                      (log.from_state = 'pending' AND log.to_state = 'returned')
                      OR (log.from_state = 'open' AND log.to_state = 'pending')
                      OR (log.from_state = 'resolved' AND log.to_state IN ('open', 'on_hold'))
                  ))
              )
        )
    """))


def downgrade() -> None:
    # Historical facts cannot be safely undone from the current flag.
    pass
