"""add ticket contact_phone

Revision ID: 5a8b1c2d3e4f
Revises: 4d7e9f1a2b3c
Create Date: 2026-07-02 16:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a8b1c2d3e4f'
down_revision: Union[str, Sequence[str], None] = '4d7e9f1a2b3c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tickets',
        sa.Column('contact_phone', sa.String(length=20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('tickets', 'contact_phone')
