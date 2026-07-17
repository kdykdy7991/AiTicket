"""add_is_draft_to_tickets

Revision ID: ae1f3078eb7b
Revises: 17c21a990230
Create Date: 2026-07-10 07:34:56.668566

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ae1f3078eb7b'
down_revision: Union[str, Sequence[str], None] = '17c21a990230'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        'tickets',
        sa.Column('is_draft', sa.Boolean(), server_default='false', nullable=False)
    )
    # 草稿无编号，number 改为可空
    op.alter_column('tickets', 'number', nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('tickets', 'number', nullable=False)
    op.drop_column('tickets', 'is_draft')
