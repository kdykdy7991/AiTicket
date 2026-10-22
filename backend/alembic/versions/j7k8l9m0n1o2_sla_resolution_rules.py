"""Replace legacy SLA matching with category rules and preserve timing rounds.

Revision ID: j7k8l9m0n1o2
Revises: i6j7k8l9m0n1
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "j7k8l9m0n1o2"
down_revision: Union[str, Sequence[str], None] = "i6j7k8l9m0n1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep legacy configuration for audit. Its department/priority key cannot be
    # translated safely into the new category-specific business rules.
    op.rename_table("sla_policies", "sla_policies_legacy")
    op.create_table(
        "sla_policies",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("category_id", sa.BigInteger(), sa.ForeignKey("ticket_categories.id", ondelete="CASCADE"), nullable=False),
        sa.Column("variant", sa.String(20), nullable=False),
        sa.Column("solution_minutes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("category_id", "variant", name="uq_sla_category_variant"),
        sa.CheckConstraint("solution_minutes > 0", name="ck_sla_solution_minutes_positive"),
    )
    # Convert the old global durations into equivalent category tiers when
    # available. Department-specific overrides have no equivalent in the new
    # category-only policy and remain visible in the archived legacy table.
    op.execute(sa.text("""
        INSERT INTO sla_policies (category_id, variant, solution_minutes)
        SELECT c.id, p.priority, p.solution_minutes
        FROM ticket_categories c JOIN sla_policies_legacy p ON p.skill_group_id IS NULL
        WHERE c.parent_id IS NULL AND c.name = '业务保障'
          AND p.priority IN ('p1_urgent','p2_high','p3_normal','p4_enterprise')
        ON CONFLICT (category_id, variant) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO sla_policies (category_id, variant, solution_minutes)
        SELECT c.id, 'default', p.solution_minutes
        FROM ticket_categories c JOIN sla_policies_legacy p
          ON p.skill_group_id IS NULL AND p.priority = 'p4_enterprise'
        WHERE c.parent_id IS NULL AND c.name NOT IN ('业务保障', '服务投诉', '投诉', '投诉类')
        ON CONFLICT (category_id, variant) DO NOTHING
    """))
    op.execute(sa.text("""
        INSERT INTO sla_policies (category_id, variant, solution_minutes)
        SELECT c.id, e.complaint_level,
               GREATEST(1, FLOOR(p.solution_minutes * e.sla_resolution_multiplier)::integer)
        FROM ticket_categories c
        JOIN sla_policies_legacy p ON p.skill_group_id IS NULL AND p.priority = 'p4_enterprise'
        JOIN complaint_escalation_policies e ON e.complaint_level IN ('一般','重要','重大')
        WHERE c.parent_id IS NULL AND c.name IN ('服务投诉', '投诉', '投诉类')
        ON CONFLICT (category_id, variant) DO NOTHING
    """))
    # Retain the old multiplier column as historical data; the new policy code
    # reads the independent duration configured for each complaint level.
    op.create_table(
        "sla_rounds",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ticket_id", sa.BigInteger(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deadline_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("breached", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.UniqueConstraint("ticket_id", "sequence", name="uq_sla_round_ticket_sequence"),
    )
    op.execute(sa.text("""
        INSERT INTO sla_rounds (ticket_id, sequence, started_at, deadline_at, ended_at, status, breached)
        SELECT id, 1, created_at, solution_deadline,
               CASE WHEN solved_at IS NOT NULL THEN solved_at
                    WHEN state = 'cancelled' THEN closed_at ELSE NULL END,
               CASE WHEN solved_at IS NOT NULL THEN 'delivered'
                    WHEN state = 'cancelled' THEN 'cancelled' ELSE 'running' END,
               sla_solution_breached
        FROM tickets WHERE is_draft = FALSE AND solution_deadline IS NOT NULL
    """))


def downgrade() -> None:
    op.drop_table("sla_rounds")
    op.drop_table("sla_policies")
    op.rename_table("sla_policies_legacy", "sla_policies")
