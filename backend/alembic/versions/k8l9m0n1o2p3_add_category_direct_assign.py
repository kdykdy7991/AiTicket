"""Add the category-level direct-assign rule column.

Revision ID: k8l9m0n1o2p3
Revises: j7k8l9m0n1o2
"""

from alembic import op
import sqlalchemy as sa


revision = "k8l9m0n1o2p3"
down_revision = "j7k8l9m0n1o2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 默认 False：默认仍走「部门对接人分派」，由分类配置显式打开
    # （seed.py 把 渠道/代理合作(1204) 标记为直指派）。
    op.add_column("ticket_categories",
                  sa.Column("direct_assign", sa.Boolean(), nullable=False, server_default=sa.false()))


def downgrade() -> None:
    op.drop_column("ticket_categories", "direct_assign")
