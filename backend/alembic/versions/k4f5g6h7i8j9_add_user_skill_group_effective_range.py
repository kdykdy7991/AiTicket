"""add effective_from/effective_to to user_skill_groups

分派设计 V0.21 数据层（docs/ticket_dispatch_design.md 表B）：
人员调岗/离职填 effective_to，不删行，保留审计回溯。
两列均可空——现有行 NULL 表示"当前生效中"，向后兼容。

注意：user_skill_groups 主键为 (user_id, skill_group_id)，同一人同部门
的历史多段生效期需要换表（department_members 代理键）才能完整表达；
当前仅提供单段生效区间，出现"离职后返岗"场景再升级。

Revision ID: k4f5g6h7i8j9
Revises: k3e4f5g6h7i8
Create Date: 2026-09-30 15:10:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k4f5g6h7i8j9"
down_revision: Union[str, Sequence[str], None] = "k3e4f5g6h7i8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "user_skill_groups",
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "user_skill_groups",
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("user_skill_groups", "effective_to")
    op.drop_column("user_skill_groups", "effective_from")
