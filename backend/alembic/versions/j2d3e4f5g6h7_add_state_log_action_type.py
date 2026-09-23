"""add ticket_state_logs.action_type

V0.86 最小架构改造 Phase 4（Flow Log action_type 增强）。

Flow Log（ticket_state_logs）新增动作类型列：
- action_type: 字符串（30），nullable —— 历史日志保持 NULL，不做回填
- 新写入的日志由 app.services.state_machine.action_for(from_state, to_state)
  从真实流转表推导（create / dispatch / hold / resume / resolve / reopen /
  return / resubmit / archive / cancel / instant_resolve）
- 非状态事件不进 Flow Log：催办仍是 Article(type=reminder)，
  SLA 超时仍由 tickets.sla_solution_breached 标记

升级语义幂等（inspect 列是否存在），便于在不同环境重复应用。

Revision ID: j2d3e4f5g6h7
Revises: i1c2d3e4f5g6
Create Date: 2026-09-23 18:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "j2d3e4f5g6h7"
down_revision: Union[str, Sequence[str], None] = "i1c2d3e4f5g6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("ticket_state_logs")}
    if "action_type" not in columns:
        op.add_column(
            "ticket_state_logs",
            sa.Column("action_type", sa.String(length=30), nullable=True),
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    columns = {c["name"] for c in inspector.get_columns("ticket_state_logs")}
    if "action_type" in columns:
        op.drop_column("ticket_state_logs", "action_type")
