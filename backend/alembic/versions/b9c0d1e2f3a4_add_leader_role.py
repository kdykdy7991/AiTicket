"""add read-only leader role

Revision ID: b9c0d1e2f3a4
Revises: a8b9c0d1e2f3
Create Date: 2026-09-14
"""

from typing import Sequence, Union

from alembic import op

revision: str = "b9c0d1e2f3a4"
down_revision: Union[str, None] = "a8b9c0d1e2f3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD_ROLES = ("admin", "presales", "approver", "taskforce", "subsystem", "quality")
NEW_ROLES = OLD_ROLES + ("leader",)


def _role_check(roles: tuple[str, ...]) -> str:
    return "role IN (" + ",".join(f"'{role}'" for role in roles) + ")"


def upgrade() -> None:
    op.drop_constraint("ck_user_roles_role_poc", "user_roles", type_="check")
    op.create_check_constraint(
        "ck_user_roles_role_poc", "user_roles", _role_check(NEW_ROLES)
    )


def downgrade() -> None:
    op.execute("DELETE FROM user_roles WHERE role = 'leader'")
    op.drop_constraint("ck_user_roles_role_poc", "user_roles", type_="check")
    op.create_check_constraint(
        "ck_user_roles_role_poc", "user_roles", _role_check(OLD_ROLES)
    )
