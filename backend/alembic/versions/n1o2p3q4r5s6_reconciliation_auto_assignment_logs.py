"""Classify reconciliation intake's automatic handoff without altering workflow history."""
from alembic import op
import sqlalchemy as sa

revision = "n1o2p3q4r5s6"
down_revision = "m0n1o2p3q4r5"
branch_labels = None
depends_on = None


def _relabel(source: str, target: str) -> None:
    # Only the first pending->open transition in the same creation transaction,
    # by the creator, for the management-review chain. Actual later dispatches
    # and the legacy sales flow are left intact; timestamps and people remain.
    op.get_bind().execute(sa.text("""
        UPDATE ticket_state_logs assigned SET action_type = :target
        FROM tickets t
        WHERE assigned.ticket_id = t.id AND t.category_id = 2204
          AND t.is_opportunity IS NOT TRUE
          AND t.dispatch_chain_steps->0->>'department_code' = '经营管理部'
          AND assigned.action_type = :source
          AND assigned.from_state = 'pending' AND assigned.to_state = 'open'
          AND assigned.operator_id = t.creator_id
          AND EXISTS (
              SELECT 1 FROM ticket_state_logs created
              WHERE created.ticket_id = t.id AND created.action_type = 'create'
                AND created.id < assigned.id AND created.created_at = assigned.created_at
                AND created.operator_id = assigned.operator_id
                AND NOT EXISTS (
                    SELECT 1 FROM ticket_state_logs middle
                    WHERE middle.ticket_id = t.id AND middle.id > created.id AND middle.id < assigned.id
                )
          )
    """), {"source": source, "target": target})


def upgrade() -> None:
    _relabel("dispatch", "auto_assign")


def downgrade() -> None:
    _relabel("auto_assign", "dispatch")
