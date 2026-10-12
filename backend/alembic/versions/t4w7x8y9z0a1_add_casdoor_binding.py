"""Bind a Casdoor OIDC subject to an existing ticket user.

Revision ID: t4w7x8y9z0a1
Revises: s3v6w7x8y9z0
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "t4w7x8y9z0a1"
down_revision: Union[str, Sequence[str], None] = "s3v6w7x8y9z0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("casdoor_issuer", sa.String(255), nullable=True))
    op.add_column("users", sa.Column("casdoor_subject", sa.String(255), nullable=True))
    op.create_unique_constraint(
        "uq_users_casdoor_identity", "users", ["casdoor_issuer", "casdoor_subject"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_users_casdoor_identity", "users", type_="unique")
    op.drop_column("users", "casdoor_subject")
    op.drop_column("users", "casdoor_issuer")
