"""Add per-user capability grants.

Revision ID: u1v2w3x4y5z6
Revises: r5s6t7u8v9w0
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "u1v2w3x4y5z6"
down_revision: Union[str, Sequence[str], None] = "r5s6t7u8v9w0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_grants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("grant_key", sa.String(length=50), nullable=False),
        sa.Column("granted_by", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_grants_user_id", "user_grants", ["user_id"])
    # No data backfill: the EXTRA_OBSERVER_USER_IDS fallback keeps existing
    # grants effective and visible in user management. The next save persists
    # them into this table, so the env whitelist can be retired safely.


def downgrade() -> None:
    op.drop_index("ix_user_grants_user_id", table_name="user_grants")
    op.drop_table("user_grants")
