"""add state log people snapshot

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-07-28 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd1e2f3a4b5c6'
down_revision: Union[str, Sequence[str], None] = 'c1d2e3f4a5b6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 写入 state_log 那一刻工单上的创建者/对接人/处理人。
    # 旧数据回填是 best-effort：拿 tickets 当前值，dispatcher 被改过的不准。
    op.add_column('ticket_state_logs', sa.Column('creator_id_snapshot', sa.BigInteger(), nullable=True))
    op.add_column('ticket_state_logs', sa.Column('dispatcher_id_snapshot', sa.BigInteger(), nullable=True))
    op.add_column('ticket_state_logs', sa.Column('owner_id_snapshot', sa.BigInteger(), nullable=True))

    op.create_foreign_key(
        'fk_state_log_creator_snap', 'ticket_state_logs', 'users',
        ['creator_id_snapshot'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_state_log_dispatcher_snap', 'ticket_state_logs', 'users',
        ['dispatcher_id_snapshot'], ['id'], ondelete='SET NULL',
    )
    op.create_foreign_key(
        'fk_state_log_owner_snap', 'ticket_state_logs', 'users',
        ['owner_id_snapshot'], ['id'], ondelete='SET NULL',
    )

    # 最佳努力回填：从 tickets 当前值拷过去
    op.execute(
        "UPDATE ticket_state_logs l "
        "SET creator_id_snapshot    = t.creator_id, "
        "    dispatcher_id_snapshot = t.dispatcher_id, "
        "    owner_id_snapshot      = t.owner_id "
        "FROM tickets t "
        "WHERE l.ticket_id = t.id"
    )


def downgrade() -> None:
    op.drop_constraint('fk_state_log_owner_snap',     'ticket_state_logs', type_='foreignkey')
    op.drop_constraint('fk_state_log_dispatcher_snap','ticket_state_logs', type_='foreignkey')
    op.drop_constraint('fk_state_log_creator_snap',   'ticket_state_logs', type_='foreignkey')
    op.drop_column('ticket_state_logs', 'owner_id_snapshot')
    op.drop_column('ticket_state_logs', 'dispatcher_id_snapshot')
    op.drop_column('ticket_state_logs', 'creator_id_snapshot')
