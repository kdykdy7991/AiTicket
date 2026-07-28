"""add ticket satisfaction

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-07-28 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e2f3a4b5c6d7'
down_revision: Union[str, Sequence[str], None] = 'd1e2f3a4b5c6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 回访满意度：仅当 is_callbacked=true 时填写
    # 值：'satisfied' / 'average' / 'dissatisfied'
    op.add_column('tickets', sa.Column('satisfaction', sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column('tickets', 'satisfaction')
