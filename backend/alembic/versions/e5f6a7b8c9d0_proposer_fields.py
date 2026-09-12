"""proposer fields

创建阶段新增业务字段：提出人、提出部门（售前组公用账号时必须手填）。

契约：docs/poc/00_poc_workflow_development_contract.md 第 5.1 节。

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("tickets", sa.Column("proposer", sa.String(length=100), nullable=True))
    op.add_column(
        "tickets", sa.Column("proposer_department", sa.String(length=100), nullable=True)
    )
    # 查询/筛选用：按提出人检索
    op.create_index("ix_tickets_proposer", "tickets", ["proposer"])


def downgrade() -> None:
    op.drop_index("ix_tickets_proposer", table_name="tickets")
    op.drop_column("tickets", "proposer_department")
    op.drop_column("tickets", "proposer")
