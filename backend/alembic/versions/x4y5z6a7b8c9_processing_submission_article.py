"""Link processing submission to its reply Article.

Revision ID: x4y5z6a7b8c9
Revises: w3x4y5z6a7b8
"""

from alembic import op
import sqlalchemy as sa

revision = "x4y5z6a7b8c9"
down_revision = "w3x4y5z6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE articles DROP CONSTRAINT IF EXISTS chk_article_type")
    op.create_check_constraint("chk_article_type", "articles",
                               "type IN ('reply', 'note', 'addition', 'reminder', 'return')")
    op.add_column("ticket_node_submissions", sa.Column("article_id", sa.BigInteger(), nullable=True))
    op.create_foreign_key("fk_node_submission_article", "ticket_node_submissions", "articles", ["article_id"], ["id"], ondelete="RESTRICT")


def downgrade() -> None:
    op.drop_constraint("fk_node_submission_article", "ticket_node_submissions", type_="foreignkey")
    op.drop_column("ticket_node_submissions", "article_id")
    op.execute("ALTER TABLE articles DROP CONSTRAINT IF EXISTS chk_article_type")
    op.create_check_constraint("chk_article_type", "articles",
                               "type IN ('reply', 'addition', 'reminder', 'return')")
