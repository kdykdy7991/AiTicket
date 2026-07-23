"""add ticket customer_phone_type

Revision ID: c1d2e3f4a5b6
Revises: b3c4d5e6f7a8
Create Date: 2026-07-23 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = '06e910a51901'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'tickets',
        sa.Column('customer_phone_type', sa.String(length=20), nullable=True),
    )
    # 已有数据按号码格式回填：命中手机号规则视为 mobile，否则视为 landline
    op.execute(
        "UPDATE tickets SET customer_phone_type = 'mobile' "
        "WHERE customer_phone ~ '^1[3-9][0-9]{9}$' "
        "AND customer_phone_type IS NULL"
    )
    op.execute(
        "UPDATE tickets SET customer_phone_type = 'landline' "
        "WHERE customer_phone_type IS NULL"
    )


def downgrade() -> None:
    op.drop_column('tickets', 'customer_phone_type')
