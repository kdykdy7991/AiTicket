"""Give existing unaffiliated handlers a temporary department.

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d0e1f2a3b4c5"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    occupied = bind.execute(sa.text(
        "SELECT name FROM skill_groups WHERE id = 121"
    )).scalar_one_or_none()
    if occupied is not None and occupied != "其他组":
        raise RuntimeError(f"skill_groups.id=121 已被其他部门占用: {occupied}")
    other_id = bind.execute(sa.text(
        "SELECT id FROM skill_groups WHERE name = '其他组'"
    )).scalar_one_or_none()
    if other_id is not None and other_id != 121:
        raise RuntimeError(f"其他组已使用非预期 ID {other_id}；先统一种子 ID")
    bind.execute(sa.text("""
        INSERT INTO skill_groups (id, name, created_at, updated_at)
        VALUES (121, '其他组', now(), now())
        ON CONFLICT (id) DO NOTHING
    """))
    bind.execute(sa.text("""
        INSERT INTO user_skill_groups (user_id, skill_group_id, is_dispatcher)
        SELECT u.id, 121, false
        FROM users u
        WHERE u.role = 'handler'
          AND NOT EXISTS (
              SELECT 1 FROM user_skill_groups usg WHERE usg.user_id = u.id
          )
        ON CONFLICT DO NOTHING
    """))
    # The customer-service agent already belongs to groups.id=1 in the
    # current data. Restore that assignment if an older environment lacks it.
    bind.execute(sa.text("""
        UPDATE users SET group_id = 1
        WHERE username = 'xiewenqian' AND role = 'agent' AND group_id IS NULL
          AND EXISTS (SELECT 1 FROM groups WHERE id = 1)
    """))
    bind.execute(sa.text("""
        SELECT setval('skill_groups_id_seq',
                      GREATEST((SELECT max(id) FROM skill_groups), 1))
    """))


def downgrade() -> None:
    # Memberships may be reassigned after deployment; leave them intact.
    pass
