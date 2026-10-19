"""Replace the sales placeholder with named handlers and repair sales drafts.

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e1f2a3b4c5d6"
down_revision: Union[str, Sequence[str], None] = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    sales_id = bind.execute(sa.text(
        "SELECT id FROM skill_groups WHERE name = '销售'"
    )).scalar_one_or_none()
    if sales_id is None:
        return  # Fresh installs create the group and users in the form seed.

    bind.execute(sa.text("""
        UPDATE tickets SET owner_id = COALESCE(owner_id, dispatcher_id), dispatcher_id = NULL
        WHERE is_draft = true AND is_opportunity = true
          AND dispatcher_id IS NOT NULL
    """))
    bind.execute(sa.text("""
        UPDATE users SET is_active = false
        WHERE username = 'sales_placeholder'
    """))
    bind.execute(sa.text("""
        DELETE FROM user_skill_groups
        WHERE skill_group_id = :sales_id
          AND user_id IN (SELECT id FROM users WHERE username = 'sales_placeholder')
    """), {"sales_id": sales_id})

    # Zhang Guanghan is an existing user; Chen Keyi may need a new account.
    bind.execute(sa.text("""
        INSERT INTO users (username, name, role, is_group_leader, password_hash, is_active, created_at, updated_at)
        SELECT 'chenkeyi', '陈可意', 'handler', false,
               '$2b$12$PlEUsC1JRHiZVoUdSUj4y.H/kzyqXWQ4jwfOkMMM3o2sb8.Bcnl/O',
               true, now(), now()
        WHERE NOT EXISTS (SELECT 1 FROM users WHERE username = 'chenkeyi' OR name = '陈可意')
    """))
    for username, name in (("zhangguanghan", "张广瀚"), ("chenkeyi", "陈可意")):
        user_id = bind.execute(sa.text("""
            SELECT id FROM users WHERE username = :username OR name = :name
            ORDER BY CASE WHEN username = :username THEN 0 ELSE 1 END LIMIT 1
        """), {"username": username, "name": name}).scalar_one_or_none()
        if user_id is None:
            continue
        bind.execute(sa.text("""
            INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher)
            VALUES (:user_id, :sales_id, false)
            ON CONFLICT (user_id, skill_group_id)
            DO UPDATE SET is_dispatcher = false
        """), {"user_id": user_id, "sales_id": sales_id})


def downgrade() -> None:
    # Keep named user accounts and historic draft ownership intact.
    pass
