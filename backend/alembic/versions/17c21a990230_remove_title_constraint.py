"""remove_title_constraint

Revision ID: 17c21a990230
Revises: 2a374c6bcec1
Create Date: 2026-07-09 18:01:41.568732

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '17c21a990230'
down_revision: Union[str, Sequence[str], None] = '2a374c6bcec1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # 将 tickets.title 改为可空，默认值 '工单'
    op.alter_column('tickets', 'title', nullable=True, server_default='工单')


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column('tickets', 'title', nullable=False, server_default=None)
