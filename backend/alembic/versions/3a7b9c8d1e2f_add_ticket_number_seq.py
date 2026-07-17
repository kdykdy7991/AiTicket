"""add ticket_number_seq

Revision ID: 3a7b9c8d1e2f
Revises: 2c9500f3f20a
Create Date: 2026-07-01 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '3a7b9c8d1e2f'
down_revision: Union[str, Sequence[str], None] = '2c9500f3f20a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create ticket_number_seq if it does not exist."""
    op.execute("CREATE SEQUENCE IF NOT EXISTS ticket_number_seq START 1")


def downgrade() -> None:
    """Drop ticket_number_seq."""
    op.execute("DROP SEQUENCE IF EXISTS ticket_number_seq")
