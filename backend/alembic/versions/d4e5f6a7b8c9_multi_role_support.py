"""multi role support

把 `users.role` 单值列改成 `user_roles` 关联表：一个用户可以拥有多个业务角色。

契约：docs/poc/00_poc_workflow_development_contract.md 第 2 节、6.4 节。

Revision ID: d4e5f6a7b8c9
Revises: c9f1a2b3d4e5
Create Date: 2026-09-12
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, None] = "c9f1a2b3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

POC_ROLES = ("admin", "presales", "approver", "taskforce", "subsystem", "quality")
_ROLE_IN = "role IN (" + ",".join(f"'{r}'" for r in POC_ROLES) + ")"


def upgrade() -> None:
    op.create_table(
        "user_roles",
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(length=20), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "role"),
        sa.CheckConstraint(_ROLE_IN, name="ck_user_roles_role_poc"),
    )
    op.create_index("ix_user_roles_role", "user_roles", ["role"])

    # 存量单角色回填为一条关联记录
    op.execute(
        sa.text(
            f"""
            INSERT INTO user_roles (user_id, role)
            SELECT id, role FROM users
             WHERE role IS NOT NULL AND {_ROLE_IN}
            ON CONFLICT DO NOTHING
            """
        )
    )

    # 单值列退场
    op.execute(sa.text("ALTER TABLE users DROP CONSTRAINT IF EXISTS ck_users_role_poc"))
    op.drop_column("users", "role")


def downgrade() -> None:
    op.add_column("users", sa.Column("role", sa.String(length=20), nullable=True))

    # 多角色回退为单角色：按固定优先级取第一个
    order = ",".join(f"'{r}'" for r in POC_ROLES)
    op.execute(
        sa.text(
            f"""
            UPDATE users u
               SET role = (
                   SELECT r.role FROM user_roles r
                    WHERE r.user_id = u.id
                    ORDER BY array_position(ARRAY[{order}], r.role)
                    LIMIT 1
               )
            """
        )
    )
    op.execute(sa.text("UPDATE users SET role = 'presales' WHERE role IS NULL OR role = ''"))
    op.alter_column("users", "role", nullable=False)
    op.create_check_constraint("ck_users_role_poc", "users", _ROLE_IN)

    op.drop_index("ix_user_roles_role", table_name="user_roles")
    op.drop_table("user_roles")
