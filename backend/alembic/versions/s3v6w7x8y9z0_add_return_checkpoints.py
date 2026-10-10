"""Persist previous workflow nodes for exact returns.

Revision ID: s3v6w7x8y9z0
Revises: r2u5v6w7x8y9
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "s3v6w7x8y9z0"
down_revision: Union[str, Sequence[str], None] = "r2u5v6w7x8y9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("return_checkpoints", sa.JSON(), nullable=False, server_default="[]"))
    op.add_column("tickets", sa.Column("legacy_return_cursor_log_id", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "legacy_return_cursor_log_id")
    op.drop_column("tickets", "return_checkpoints")
