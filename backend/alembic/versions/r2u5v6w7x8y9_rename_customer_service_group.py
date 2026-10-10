"""Use the customer service group name for the original default group.

Revision ID: r2u5v6w7x8y9
Revises: q1t4u5v6w7x8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "r2u5v6w7x8y9"
down_revision: Union[str, Sequence[str], None] = "q1t4u5v6w7x8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("""
        UPDATE groups
        SET name = '客服组', updated_at = CURRENT_TIMESTAMP
        WHERE id = 1 AND name IN ('默认组', '客服一组')
    """))


def downgrade() -> None:
    pass
