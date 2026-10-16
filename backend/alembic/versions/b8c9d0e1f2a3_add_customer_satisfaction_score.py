"""Add an independent 1-10 customer satisfaction score.

Revision ID: b8c9d0e1f2a3
Revises: a7b8c9d0e1f2
"""

from alembic import op
import sqlalchemy as sa


revision = "b8c9d0e1f2a3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("customer_satisfaction_score", sa.Integer(), nullable=True))
    op.create_check_constraint("ck_ticket_customer_satisfaction_score_range", "tickets",
                               "customer_satisfaction_score BETWEEN 1 AND 10")


def downgrade() -> None:
    op.drop_constraint("ck_ticket_customer_satisfaction_score_range", "tickets", type_="check")
    op.drop_column("tickets", "customer_satisfaction_score")
