"""Keep the identity-provider username when a ticket username is renamed."""
from alembic import op
import sqlalchemy as sa

revision = "r5s6t7u8v9w0"
down_revision = "q4r5s6t7u8v9"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("users", sa.Column("casdoor_login_username", sa.String(50), nullable=True))


def downgrade():
    op.drop_column("users", "casdoor_login_username")
