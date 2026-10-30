"""Preserve each hold's expected resume time in its state log."""
from alembic import op
import sqlalchemy as sa

revision = "o2p3q4r5s6t7"
down_revision = "n1o2p3q4r5s6"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ticket_state_logs", sa.Column("hold_until_snapshot", sa.DateTime(timezone=True), nullable=True))
    op.execute("""UPDATE ticket_state_logs AS l SET hold_until_snapshot = t.hold_until
        FROM tickets AS t WHERE t.id = l.ticket_id AND t.state = 'on_hold'
        AND l.id = (SELECT MAX(id) FROM ticket_state_logs WHERE ticket_id = t.id AND action_type = 'hold')""")


def downgrade():
    op.drop_column("ticket_state_logs", "hold_until_snapshot")
