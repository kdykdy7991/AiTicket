"""Enable intake assignment for package change tickets."""
from alembic import op
import sqlalchemy as sa

revision = "m0n1o2p3q4r5"
down_revision = "l9m0n1o2p3q4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE ticket_categories SET direct_assign = true WHERE id = 2203"))


def downgrade() -> None:
    op.get_bind().execute(sa.text("UPDATE ticket_categories SET direct_assign = false WHERE id = 2203"))
