"""add ticket root_cause and solution

Phase 7 of the responsibility/flow overhaul.

Adds two structured processing fields to tickets:
- root_cause: 根本原因（处理人填写）
- solution:   解决办法（处理人填写）

Both nullable. Existing `resolution` (Text) is preserved for backwards
compatibility (already wired into the resolved / archived flow and the
前端's "处理结果" detail page).

Historical tickets remain without them; no automatic backfill is performed.

Revision ID: h1b2c3d4e5f6
Revises: g1a2b3c4d5e6
Create Date: 2026-09-21 16:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "h1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "g1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("root_cause", sa.Text(), nullable=True))
    op.add_column("tickets", sa.Column("solution", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "solution")
    op.drop_column("tickets", "root_cause")