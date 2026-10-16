"""Add the hold expiry reminder de-dup marker.

Revision ID: a7b8c9d0e1f2
Revises: z6a7b8c9d0e1
"""

from alembic import op
import sqlalchemy as sa


revision = "a7b8c9d0e1f2"
down_revision = "z6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 只用于「预计恢复时间已到」提醒的去重，不承载任何 SLA 语义。
    op.add_column("tickets",
                  sa.Column("hold_reminded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "hold_reminded_at")
