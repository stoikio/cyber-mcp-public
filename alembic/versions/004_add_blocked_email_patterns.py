"""Add blocked_email_patterns table for admin-managed login restrictions.

Revision ID: 004
Revises: 003
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "004"
down_revision = "003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "blocked_email_patterns",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pattern", sa.String(255), unique=True, nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.execute(
        "INSERT INTO blocked_email_patterns (pattern, description) "
        "VALUES ('^admin\\..*@example\\.com$', 'Administrative accounts (admin.*@example.com)')"
    )


def downgrade() -> None:
    op.drop_table("blocked_email_patterns")
