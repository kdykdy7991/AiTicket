"""Rename complaint coordinator placeholder and permit its local password login.

Revision ID: g3b4c5d6e7f8
Revises: f2a3b4c5d6e8
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g3b4c5d6e7f8"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("local_login_enabled", sa.Boolean(), nullable=False,
                                      server_default=sa.false()))
    op.execute(sa.text("""
        UPDATE users SET username = '服务投诉协调人占位账号',
            name = '服务投诉协调人', role = 'handler', group_id = NULL,
            local_login_enabled = true, updated_at = now()
        WHERE username = 'v2_dispatcher_complaint'
    """))


def downgrade() -> None:
    op.execute(sa.text("""
        UPDATE users SET username = 'v2_dispatcher_complaint',
            role = 'agent', group_id = 1, updated_at = now()
        WHERE username = '服务投诉协调人占位账号'
    """))
    op.drop_column("users", "local_login_enabled")
