"""Remove the ticket urge (reminder) feature.

下线「催办」功能：
1. 删除 reminders 表（早期 Reminder 模型，数据已并入 Article(type='reminder')）。
2. 删除 tickets.urged_at / tickets.urged_by_id 两列及索引。
3. 清理 articles 中历史 type='reminder' 沟通记录，并把 chk_article_type
   约束收敛为 reply / note / addition / return。

Revision ID: i6j7k8l9m0n1
Revises: i5d6e7f8g9h0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "i6j7k8l9m0n1"
down_revision: Union[str, Sequence[str], None] = "i5d6e7f8g9h0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    # 催办沟通记录（Article type='reminder'）随功能一并清理。
    bind.execute(sa.text("DELETE FROM articles WHERE type = 'reminder'"))
    # 旧 Reminder 表（早期实现，已废弃）整体删除。
    bind.execute(sa.text("DROP TABLE IF EXISTS reminders"))
    # tickets 催办字段。
    bind.execute(sa.text("ALTER TABLE tickets DROP COLUMN IF EXISTS urged_at"))
    bind.execute(sa.text("ALTER TABLE tickets DROP COLUMN IF EXISTS urged_by_id"))
    bind.execute(sa.text("DROP INDEX IF EXISTS idx_tickets_urged_at"))
    # articles 类型约束去掉 reminder。
    bind.execute(sa.text("ALTER TABLE articles DROP CONSTRAINT IF EXISTS chk_article_type"))
    bind.execute(sa.text(
        "ALTER TABLE articles ADD CONSTRAINT chk_article_type "
        "CHECK (type IN ('reply', 'note', 'addition', 'return'))"
    ))


def downgrade() -> None:
    bind = op.get_bind()
    # 恢复约束（允许 reminder）。
    bind.execute(sa.text("ALTER TABLE articles DROP CONSTRAINT IF EXISTS chk_article_type"))
    bind.execute(sa.text(
        "ALTER TABLE articles ADD CONSTRAINT chk_article_type "
        "CHECK (type IN ('reply', 'note', 'addition', 'reminder', 'return'))"
    ))
    # 恢复 tickets 催办字段（历史数据不可重建，仅恢复结构）。
    bind.execute(sa.text(
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS urged_at TIMESTAMPTZ"
    ))
    bind.execute(sa.text(
        "ALTER TABLE tickets ADD COLUMN IF NOT EXISTS "
        "urged_by_id BIGINT REFERENCES users(id) ON DELETE SET NULL"
    ))
    bind.execute(sa.text(
        "CREATE INDEX IF NOT EXISTS idx_tickets_urged_at "
        "ON tickets(urged_at) WHERE urged_at IS NOT NULL"
    ))
    # 恢复旧 reminders 表（结构与 001_init_schema.sql 一致）。
    op.create_table(
        "reminders",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("ticket_id", sa.BigInteger(), nullable=False),
        sa.Column("sender_id", sa.BigInteger(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["sender_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["ticket_id"], ["tickets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
