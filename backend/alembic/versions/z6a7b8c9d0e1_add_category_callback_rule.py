"""Add the category-level callback rule column.

Revision ID: z6a7b8c9d0e1
Revises: y5z6a7b8c9d0
"""

from alembic import op
import sqlalchemy as sa


revision = "z6a7b8c9d0e1"
down_revision = "y5z6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 默认 False：默认不要求回访，由分类配置显式打开（seed.py 设置规则分类）。
    # 存量分类保持 False；存量工单的 tickets.callback_required 是已记录事实，不在此回填。
    op.add_column("ticket_categories",
                  sa.Column("requires_callback", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("ticket_categories", "requires_callback")
