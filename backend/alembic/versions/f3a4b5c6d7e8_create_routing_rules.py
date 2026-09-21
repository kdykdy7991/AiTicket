"""create category_routing_rules table

Phase 3 of the responsibility/flow overhaul.

Each row binds a final category to:
- dispatcher_skill_group_id (coordinator department)
- dispatcher_id              (coordinator user)
- handler_skill_group_id     (professional department, nullable)
- owner_id                   (default professional handler, nullable)

UNIQUE(category_id) so each category has at most one default rule.
Historical tickets are NOT affected.

Revision ID: f3a4b5c6d7e8
Revises: f2a3b4c5d6e7
Create Date: 2026-09-21 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f3a4b5c6d7e8"
down_revision: Union[str, Sequence[str], None] = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "category_routing_rules",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("dispatcher_skill_group_id", sa.BigInteger(), nullable=False),
        sa.Column("dispatcher_id", sa.BigInteger(), nullable=False),
        sa.Column("handler_skill_group_id", sa.BigInteger(), nullable=True),
        sa.Column("owner_id", sa.BigInteger(), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["category_id"], ["ticket_categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["dispatcher_skill_group_id"], ["skill_groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["handler_skill_group_id"], ["skill_groups.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["dispatcher_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", name="uq_routing_category"),
    )
    op.create_index(
        "ix_category_routing_rules_category", "category_routing_rules", ["category_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_category_routing_rules_category", table_name="category_routing_rules")
    op.drop_table("category_routing_rules")
