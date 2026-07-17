"""add ticket has_addition

Revision ID: 6b7c8d9e1a2f
Revises: 5a8b1c2d3e4f
Create Date: 2026-07-03 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6b7c8d9e1a2f'
down_revision: Union[str, Sequence[str], None] = '5a8b1c2d3e4f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tickets',
        sa.Column('has_addition', sa.Boolean(), nullable=False, server_default=sa.text('false')),
    )
    # 回溯：历史上已有 addition 类型 article 的工单也打上标记
    op.execute(
        "UPDATE tickets SET has_addition = true WHERE EXISTS ("
        "SELECT 1 FROM articles WHERE articles.ticket_id = tickets.id AND articles.type = 'addition'"
        ")"
    )


def downgrade() -> None:
    op.drop_column('tickets', 'has_addition')
