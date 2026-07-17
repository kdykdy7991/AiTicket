"""make customer_name nullable

Revision ID: b3c4d5e6f7a8
Revises: ae1f3078eb7b
Create Date: 2026-07-10 11:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'b3c4d5e6f7a8'
down_revision = 'ae1f3078eb7b'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 将 customer_name 字段改为可空
    op.alter_column('tickets', 'customer_name',
                     existing_type=sa.String(length=100),
                     nullable=True)


def downgrade() -> None:
    # 恢复 customer_name 字段为非空
    op.alter_column('tickets', 'customer_name',
                     existing_type=sa.String(length=100),
                     nullable=False)
