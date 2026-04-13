"""Initial schema — 5 tables for Option C persistence.

Revision ID: 001
Revises:
Create Date: 2026-04-08
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, JSONB

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. oauth_clients
    op.create_table(
        "oauth_clients",
        sa.Column("client_id", sa.String(64), primary_key=True),
        sa.Column("client_name", sa.String(255), nullable=False),
        sa.Column("redirect_uris", JSONB, nullable=False, server_default="[]"),
        sa.Column("grant_types", JSONB, server_default='["authorization_code"]'),
        sa.Column("response_types", JSONB, server_default='["code"]'),
        sa.Column("auth_method", sa.String(32), server_default="none"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # 2. user_tokens
    op.create_table(
        "user_tokens",
        sa.Column("email", sa.String(255), primary_key=True),
        sa.Column("encrypted_token_data", sa.Text, nullable=False),
        sa.Column("scopes", ARRAY(sa.Text), server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("last_refreshed_at", sa.DateTime(timezone=True), nullable=True),
    )

    # 3. api_keys
    op.create_table(
        "api_keys",
        sa.Column("key_hash", sa.String(64), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked", sa.Boolean, nullable=False, server_default="false"),
    )
    op.create_index("idx_apikeys_email", "api_keys", ["email"])

    # 4. audit_events
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ts", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("event", sa.String(64), nullable=False),
        sa.Column("user_email", sa.String(255), server_default=""),
        sa.Column("tool", sa.String(64), server_default=""),
        sa.Column("details", JSONB, server_default="{}"),
        sa.Column("ip", sa.String(45), server_default=""),
    )
    op.create_index("idx_audit_user", "audit_events", ["user_email"])
    op.create_index("idx_audit_ts", "audit_events", ["ts"])
    op.create_index("idx_audit_event", "audit_events", ["event"])

    # 5. policies
    op.create_table(
        "policies",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(128), unique=True, nullable=False),
        sa.Column("description", sa.Text, server_default=""),
        sa.Column("tool_pattern", sa.String(128), nullable=False, server_default="*"),
        sa.Column("action", sa.String(16), nullable=False, server_default="block"),
        sa.Column("conditions", JSONB, nullable=False, server_default="{}"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("policies")
    op.drop_table("audit_events")
    op.drop_table("api_keys")
    op.drop_table("user_tokens")
    op.drop_table("oauth_clients")
