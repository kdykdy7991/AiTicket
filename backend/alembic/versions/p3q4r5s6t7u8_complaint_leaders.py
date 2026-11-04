"""Add complaint responsibilities to department memberships."""
from alembic import op
import sqlalchemy as sa

revision = "p3q4r5s6t7u8"
down_revision = "o2p3q4r5s6t7"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("user_skill_groups", sa.Column("complaint_leader", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("user_skill_groups", sa.Column("complaint_division_leader", sa.Boolean(), nullable=False, server_default=sa.false()))

def downgrade():
    op.drop_column("user_skill_groups", "complaint_division_leader")
    op.drop_column("user_skill_groups", "complaint_leader")
