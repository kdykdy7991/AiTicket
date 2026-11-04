"""Associate complaint topics with department leaders."""
from alembic import op
import sqlalchemy as sa

revision = "q4r5s6t7u8v9"
down_revision = "p3q4r5s6t7u8"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("user_skill_groups", sa.Column("complaint_responsibilities", sa.JSON(), nullable=False, server_default="[]"))

def downgrade():
    op.drop_column("user_skill_groups", "complaint_responsibilities")
