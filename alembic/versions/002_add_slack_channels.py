"""Add slack_channels table for configurable channel reading.

Revision ID: 002
Revises: 001
Create Date: 2026-04-09
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "slack_channels",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("channel_id", sa.String(32), unique=True, nullable=False),
        sa.Column("channel_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("max_messages", sa.Integer, nullable=False, server_default="50"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("slack_channels")
