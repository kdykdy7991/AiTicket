"""add ticket handler_skill_group_id

Phase 4 of the responsibility/flow overhaul.

Add a nullable FK tickets.handler_skill_group_id -> skill_groups.id.

Semantics:
- skill_group_id        = 协调部门 (coordinator department, unchanged)
- handler_skill_group_id = 专业处理部门 (professional department, NEW)

For historical tickets this column is NULL, which means:
- the original behavior (use skill_group_id only) continues to work
- filters/list views that target the new column simply return nothing for old rows

The new column is backfilled only when a routing rule is applied or an admin
sets it explicitly. No automatic backfill is performed to avoid mass-editing
historical tickets.

Revision ID: g1a2b3c4d5e6
Revises: f3a4b5c6d7e8
Create Date: 2026-09-21 14:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "g1a2b3c4d5e6"
down_revision: Union[str, Sequence[str], None] = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column(
            "handler_skill_group_id",
            sa.BigInteger(),
            nullable=True,
        ),
    )
    op.create_foreign_key(
        "fk_tickets_handler_skill_group",
        "tickets",
        "skill_groups",
        ["handler_skill_group_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_tickets_handler_skill_group",
        "tickets",
        ["handler_skill_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tickets_handler_skill_group", table_name="tickets")
    op.drop_constraint("fk_tickets_handler_skill_group", "tickets", type_="foreignkey")
    op.drop_column("tickets", "handler_skill_group_id")