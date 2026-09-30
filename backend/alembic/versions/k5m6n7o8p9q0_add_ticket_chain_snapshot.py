"""add dispatch_chain_steps / dispatch_step_index to tickets

分派设计 V0.21 链快照（docs/ticket_dispatch_design.md §3、§8.2 #4）：
- 建单/分诊时把 dispatch_chains.steps 展开写入工单，后续按快照推进；
- dispatch_step_index 指向当前步骤（0 起），多步链转派时递增；
- 两列均可空：不走链的工单（旧 category_routing_rules / 即时办结）为 NULL。

Revision ID: k5m6n7o8p9q0
Revises: k4f5g6h7i8j9
Create Date: 2026-09-30 16:30:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k5m6n7o8p9q0"
down_revision: Union[str, Sequence[str], None] = "k4f5g6h7i8j9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("dispatch_chain_steps", sa.JSON(), nullable=True))
    op.add_column("tickets", sa.Column("dispatch_step_index", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("tickets", "dispatch_step_index")
    op.drop_column("tickets", "dispatch_chain_steps")
