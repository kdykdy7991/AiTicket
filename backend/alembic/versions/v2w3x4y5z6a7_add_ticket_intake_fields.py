"""Persist fields collected by the new ticket intake form.

Revision ID: v2w3x4y5z6a7
Revises: u5x8y9z0a1b2
"""
from alembic import op
import sqlalchemy as sa

revision = 'v2w3x4y5z6a7'
down_revision = 'u5x8y9z0a1b2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('tickets', sa.Column('industry', sa.String(50), nullable=True))
    op.add_column('tickets', sa.Column('customer_email', sa.String(255), nullable=True))
    op.add_column('tickets', sa.Column('satellite_number', sa.String(100), nullable=True))
    op.add_column('tickets', sa.Column('is_opportunity', sa.Boolean(), nullable=True))
    op.add_column('tickets', sa.Column('expected_result', sa.String(50), nullable=True))
    op.add_column('tickets', sa.Column('fault_occurred_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('tickets', sa.Column('fault_recurrence', sa.String(30), nullable=True))
    op.add_column('tickets', sa.Column('fault_location', sa.String(255), nullable=True))
    op.add_column('tickets', sa.Column('is_batch_fault', sa.Boolean(), nullable=True))


def downgrade() -> None:
    for column in ('is_batch_fault', 'fault_location', 'fault_recurrence', 'fault_occurred_at',
                   'expected_result', 'is_opportunity', 'satellite_number', 'customer_email', 'industry'):
        op.drop_column('tickets', column)
