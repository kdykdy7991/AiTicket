"""create dispatch_chains table

分派设计 V0.21 数据层第一步（docs/ticket_dispatch_design.md §8.3）：
- 每分类一条链（category_id UNIQUE），steps 为部门代称 JSON 数组；
- 与 category_routing_rules 双轨并存，旧表暂不下线。

Revision ID: k3e4f5g6h7i8
Revises: j2d3e4f5g6h7
Create Date: 2026-09-30 15:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "k3e4f5g6h7i8"
down_revision: Union[str, Sequence[str], None] = "j2d3e4f5g6h7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dispatch_chains",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("category_id", sa.BigInteger(), nullable=False),
        sa.Column("steps", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["category_id"], ["ticket_categories.id"],
                                ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("category_id", name="uq_dispatch_chain_category"),
    )
    op.create_index("ix_dispatch_chains_category_id", "dispatch_chains",
                    ["category_id"])


def downgrade() -> None:
    op.drop_index("ix_dispatch_chains_category_id", table_name="dispatch_chains")
    op.drop_table("dispatch_chains")
