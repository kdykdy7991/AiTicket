"""Add structured closeout fields used by the closure node form.

Revision ID: y5z6a7b8c9d0
Revises: x4y5z6a7b8c9
"""

from alembic import op
import sqlalchemy as sa


revision = "y5z6a7b8c9d0"
down_revision = "x4y5z6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 关单结果：受控枚举，面向关单口径统计；历史行保持 NULL。
    op.add_column("tickets", sa.Column("closure_result", sa.String(30), nullable=True))
    # 客户是否认可：与 satisfaction 分档相互独立；NULL 表示尚未记录。
    op.add_column("tickets", sa.Column("customer_recognized", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "customer_recognized")
    op.drop_column("tickets", "closure_result")