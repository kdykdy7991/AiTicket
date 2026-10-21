"""Add independent visit records for historical hotline and online contacts.

Revision ID: i5d6e7f8g9h0
Revises: h4c5d6e7f8g9
"""

from alembic import op
import sqlalchemy as sa


revision = "i5d6e7f8g9h0"
down_revision = "h4c5d6e7f8g9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "visit_records",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("source_sheet", sa.String(80)),
        sa.Column("source_row", sa.Integer()),
        sa.Column("contact_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contact_number", sa.String(100)),
        sa.Column("customer_name", sa.String(100)),
        sa.Column("service_agent", sa.String(100)),
        sa.Column("channel", sa.String(40), nullable=False),
        sa.Column("category_l1", sa.String(100)),
        sa.Column("category_l2", sa.String(100)),
        sa.Column("registered_ticket", sa.Boolean()),
        sa.Column("fields", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("source_sheet", "source_row", name="uq_visit_records_source"),
    )
    op.create_index("ix_visit_records_contact_at", "visit_records", ["contact_at"])
    op.create_index("ix_visit_records_contact_number", "visit_records", ["contact_number"])
    op.create_index("ix_visit_records_category_l1", "visit_records", ["category_l1"])


def downgrade() -> None:
    op.drop_table("visit_records")
