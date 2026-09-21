"""add ticket complaint_level and complaint_escalation_policies

Phase 8 of the responsibility/flow overhaul.

Two additions:
1. tickets.complaint_level: enum-like string ("一般"/"重要"/"重大") on
   service-complaint tickets. NULL on non-complaint tickets.

2. complaint_escalation_policies: per-level escalation config:
   - complaint_level (UNIQUE)
   - notify_skill_group_id (which team gets notified on creation, nullable)
   - sla_resolution_multiplier (e.g. 0.5 = cut SLA in half for 重大)
   - required_role (e.g. 'manager' for 重要, 'admin' for 重大) — text only,
     enforced in API layer via existing require_role helper

Historical tickets stay NULL; no automatic backfill.
Default policies are seeded for the three levels (idempotent).

Revision ID: i1c2d3e4f5g6
Revises: h1b2c3d4e5f6
Create Date: 2026-09-21 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i1c2d3e4f5g6"
down_revision: Union[str, Sequence[str], None] = "h1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tickets",
        sa.Column("complaint_level", sa.String(length=20), nullable=True),
    )
    op.create_index(
        "ix_tickets_complaint_level",
        "tickets",
        ["complaint_level"],
    )

    op.create_table(
        "complaint_escalation_policies",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("complaint_level", sa.String(length=20), nullable=False),
        sa.Column("notify_skill_group_id", sa.BigInteger(), nullable=True),
        sa.Column("sla_resolution_multiplier", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("required_role", sa.String(length=20), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["notify_skill_group_id"], ["skill_groups.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("complaint_level", name="uq_complaint_level"),
    )

    # Default policies (idempotent via UNIQUE on complaint_level).
    # Values inlined (sa.text + params binding isn't reliable with asyncpg via alembic).
    op.execute(
        "INSERT INTO complaint_escalation_policies "
        "(complaint_level, sla_resolution_multiplier, required_role, note, created_at, updated_at) "
        "VALUES ('一般', 1.0, 'agent', '默认 一般 投诉级别策略', NOW(), NOW()) "
        "ON CONFLICT (complaint_level) DO NOTHING"
    )
    op.execute(
        "INSERT INTO complaint_escalation_policies "
        "(complaint_level, sla_resolution_multiplier, required_role, note, created_at, updated_at) "
        "VALUES ('重要', 0.75, 'manager', '默认 重要 投诉级别策略', NOW(), NOW()) "
        "ON CONFLICT (complaint_level) DO NOTHING"
    )
    op.execute(
        "INSERT INTO complaint_escalation_policies "
        "(complaint_level, sla_resolution_multiplier, required_role, note, created_at, updated_at) "
        "VALUES ('重大', 0.5, 'admin', '默认 重大 投诉级别策略', NOW(), NOW()) "
        "ON CONFLICT (complaint_level) DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table("complaint_escalation_policies")
    op.drop_index("ix_tickets_complaint_level", table_name="tickets")
    op.drop_column("tickets", "complaint_level")