"""rename seeded leader accounts

Revision ID: c0d1e2f3a4b5
Revises: b9c0d1e2f3a4
Create Date: 2026-09-14
"""

from typing import Sequence, Union

from alembic import op

revision: str = "c0d1e2f3a4b5"
down_revision: Union[str, None] = "b9c0d1e2f3a4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _rename_or_disable(old_username: str, new_username: str) -> None:
    # 若目标账号尚不存在则原地改名，保留用户 ID 及所有关联数据；
    # 若目标已存在则停用旧账号，避免唯一键冲突和重复登录账号。
    op.execute(
        f"""
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM users WHERE username = '{old_username}')
               AND NOT EXISTS (SELECT 1 FROM users WHERE username = '{new_username}') THEN
                UPDATE users
                   SET username = '{new_username}', updated_at = now()
                 WHERE username = '{old_username}';
            ELSIF EXISTS (SELECT 1 FROM users WHERE username = '{old_username}') THEN
                UPDATE users
                   SET is_active = false, updated_at = now()
                 WHERE username = '{old_username}';
            END IF;
        END $$;
        """
    )


def upgrade() -> None:
    _rename_or_disable("leader01", "Tony")
    _rename_or_disable("leader02", "Edison")


def downgrade() -> None:
    _rename_or_disable("Tony", "leader01")
    _rename_or_disable("Edison", "leader02")
