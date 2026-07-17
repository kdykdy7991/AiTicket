"""add_return_article_type

Revision ID: 2a374c6bcec1
Revises: 7c8d9e1f2a3b
Create Date: 2026-07-06 17:23:00.065393

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2a374c6bcec1'
down_revision: Union[str, Sequence[str], None] = '7c8d9e1f2a3b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Allow article type 'return' for system-generated return records."""
    # 使用 IF EXISTS，兼容部分环境未创建该约束的情况
    op.execute("ALTER TABLE articles DROP CONSTRAINT IF EXISTS chk_article_type")
    op.create_check_constraint(
        'chk_article_type',
        'articles',
        "type IN ('reply', 'addition', 'reminder', 'return')"
    )


def downgrade() -> None:
    """Remove 'return' article type."""
    op.execute("ALTER TABLE articles DROP CONSTRAINT IF EXISTS chk_article_type")
    op.create_check_constraint(
        'chk_article_type',
        'articles',
        "type IN ('reply', 'addition', 'reminder')"
    )
