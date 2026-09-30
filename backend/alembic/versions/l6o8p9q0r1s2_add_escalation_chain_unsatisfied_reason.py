"""add complaint escalation_chain and ticket unsatisfied_reason

Design closeout (设计 §5.2 / §8.2 #6、#9):

1. complaint_escalation_policies.escalation_chain (JSON, nullable):
   动态角色升级链，role 不绑具体人。
   一般 = NULL（走 dispatch_chain → 值班组）；
   重要 = [部门负责人]；重大 = [部门负责人 → 分管领导]。
   steps 同构 dispatch_chains.steps 的 order 语义。

2. tickets.unsatisfied_reason (Text, nullable):
   回访满意度为 dissatisfied 时必填的原因。
   退回重开后保留，新一轮回访若为非不满意则清空。

Revision ID: l6o8p9q0r1s2
Revises: k5m6n7o8p9q0
Create Date: 2026-09-30 12:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "l6o8p9q0r1s2"
down_revision: Union[str, Sequence[str], None] = "k5m6n7o8p9q0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "complaint_escalation_policies",
        sa.Column("escalation_chain", sa.JSON(), nullable=True),
    )
    op.add_column(
        "tickets",
        sa.Column("unsatisfied_reason", sa.Text(), nullable=True),
    )

    # Seed 重要 / 重大 升级链（一般 保持 NULL）。
    # exec_driver_sql：JSON 字面量含 "order":1 这类 `:x` 序列，走 SQLAlchemy
    # text() 会被误解析成绑定参数（InvalidRequestError: bind parameter '1'）。
    op.get_bind().exec_driver_sql(
        "UPDATE complaint_escalation_policies SET escalation_chain = "
        "'[{\"order\":1,\"role\":\"dept_leader\",\"label\":\"涉及部门负责人\"}]'::json "
        "WHERE complaint_level = '重要'"
    )
    op.get_bind().exec_driver_sql(
        "UPDATE complaint_escalation_policies SET escalation_chain = "
        "'[{\"order\":1,\"role\":\"dept_leader\",\"label\":\"涉及部门负责人\"},"
        "{\"order\":2,\"role\":\"division_leader\",\"label\":\"分管领导\"}]'::json "
        "WHERE complaint_level = '重大'"
    )


def downgrade() -> None:
    op.drop_column("tickets", "unsatisfied_reason")
    op.drop_column("complaint_escalation_policies", "escalation_chain")
