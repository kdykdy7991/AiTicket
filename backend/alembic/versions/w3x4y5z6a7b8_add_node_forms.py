"""Add published node forms and historical submissions.

Revision ID: w3x4y5z6a7b8
Revises: v2w3x4y5z6a7
"""

from alembic import op
import sqlalchemy as sa

revision = "w3x4y5z6a7b8"
down_revision = "v2w3x4y5z6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "form_definitions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(100), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("node_type", sa.String(40), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("code", "version"),
    )
    op.create_table(
        "form_field_definitions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("form_definition_id", sa.BigInteger(), sa.ForeignKey("form_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("field_key", sa.String(100), nullable=False),
        sa.Column("label", sa.String(200), nullable=False),
        sa.Column("field_type", sa.String(40), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("options", sa.JSON()),
        sa.Column("validation", sa.JSON()),
        sa.Column("visibility_condition", sa.JSON()),
        sa.Column("required_condition", sa.JSON()),
        sa.Column("storage_type", sa.String(30), nullable=False),
        sa.Column("storage_key", sa.String(100)),
        sa.UniqueConstraint("form_definition_id", "field_key"),
    )
    op.create_table(
        "form_bindings",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("node_type", sa.String(40), nullable=False),
        sa.Column("department_code", sa.String(100)),
        sa.Column("category_id", sa.BigInteger(), sa.ForeignKey("ticket_categories.id", ondelete="RESTRICT")),
        sa.Column("category_match_type", sa.String(30), nullable=False),
        sa.Column("form_definition_id", sa.BigInteger(), sa.ForeignKey("form_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
    )
    op.create_table(
        "ticket_node_submissions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("ticket_id", sa.BigInteger(), sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_type", sa.String(40), nullable=False),
        sa.Column("form_definition_id", sa.BigInteger(), sa.ForeignKey("form_definitions.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("form_version", sa.Integer(), nullable=False),
        sa.Column("department_id", sa.BigInteger(), sa.ForeignKey("skill_groups.id", ondelete="SET NULL")),
        sa.Column("operator_id", sa.BigInteger(), sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("field_snapshot", sa.JSON(), nullable=False),
        sa.Column("state_log_id", sa.BigInteger(), sa.ForeignKey("ticket_state_logs.id", ondelete="SET NULL")),
    )
    op.create_index("ix_node_submissions_ticket", "ticket_node_submissions", ["ticket_id", "submitted_at"])


def downgrade() -> None:
    op.drop_index("ix_node_submissions_ticket", table_name="ticket_node_submissions")
    for table in ("ticket_node_submissions", "form_bindings", "form_field_definitions", "form_definitions"):
        op.drop_table(table)
