"""Add integration_tokens table for admin-managed service credentials.

Revision ID: 003
Revises: 002
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "003"
down_revision = "002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "integration_tokens",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("service", sa.String(32), unique=True, nullable=False),
        sa.Column("encrypted_value", sa.Text, nullable=False),
        sa.Column("label", sa.String(255), server_default=""),
        sa.Column("updated_by", sa.String(255), server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("integration_tokens")
