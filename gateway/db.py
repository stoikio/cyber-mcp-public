"""
SQLAlchemy async engine, session factory, et modèles ORM.
8 tables : oauth_clients, user_tokens, api_keys, audit_events, policies,
           slack_channels, integration_tokens, blocked_email_patterns.
"""

import ssl
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from gateway.config import DATABASE_URL, DATABASE_POOL_SIZE, DATABASE_POOL_OVERFLOW, DATABASE_SSL

# ─── Engine & Session ────────────────────────────────────────────

_connect_args: dict = {}
if DATABASE_SSL:
    _ssl_ctx = ssl.create_default_context()
    _ssl_ctx.check_hostname = False
    _ssl_ctx.verify_mode = ssl.CERT_NONE
    _connect_args["ssl"] = _ssl_ctx

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_size=DATABASE_POOL_SIZE,
    max_overflow=DATABASE_POOL_OVERFLOW,
    connect_args=_connect_args,
    pool_pre_ping=True,
)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


# ─── Models ──────────────────────────────────────────────────────


class OAuthClient(Base):
    """RFC 7591 Dynamic Client Registration — persisté en PG."""

    __tablename__ = "oauth_clients"

    client_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    client_name: Mapped[str] = mapped_column(String(255), nullable=False)
    redirect_uris: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="[]")
    grant_types: Mapped[dict] = mapped_column(JSONB, server_default='["authorization_code"]')
    response_types: Mapped[dict] = mapped_column(JSONB, server_default='["code"]')
    auth_method: Mapped[str] = mapped_column(String(32), server_default="none")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class UserToken(Base):
    """Tokens Google OAuth2 par utilisateur (chiffrés Fernet)."""

    __tablename__ = "user_tokens"

    email: Mapped[str] = mapped_column(String(255), primary_key=True)
    encrypted_token_data: Mapped[str] = mapped_column(Text, nullable=False)
    scopes: Mapped[list] = mapped_column(ARRAY(Text), server_default="{}")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_refreshed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class ApiKey(Base):
    """Clés API hachées SHA-256 avec expiration et révocation."""

    __tablename__ = "api_keys"

    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    revoked: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")


class AuditEvent(Base):
    """Événements d'audit structurés (remplace audit.log)."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    event: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    user_email: Mapped[str] = mapped_column(String(255), server_default="", index=True)
    tool: Mapped[str] = mapped_column(String(64), server_default="")
    details: Mapped[dict] = mapped_column(JSONB, server_default="{}")
    ip: Mapped[str] = mapped_column(String(45), server_default="")


class Policy(Base):
    """Politiques de sécurité (remplace policies.json)."""

    __tablename__ = "policies"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, server_default="")
    tool_pattern: Mapped[str] = mapped_column(String(128), nullable=False, server_default="*")
    action: Mapped[str] = mapped_column(String(16), nullable=False, server_default="block")
    conditions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    priority: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class SlackChannel(Base):
    """Canaux Slack autorisés pour la lecture via le gateway."""

    __tablename__ = "slack_channels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    channel_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    channel_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text, server_default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    max_messages: Mapped[int] = mapped_column(Integer, nullable=False, server_default="50")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class IntegrationToken(Base):
    """Tokens d'intégration (Slack, Notion, etc.) chiffrés Fernet."""

    __tablename__ = "integration_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    service: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)
    encrypted_value: Mapped[str] = mapped_column(Text, nullable=False)
    label: Mapped[str] = mapped_column(String(255), server_default="")
    updated_by: Mapped[str] = mapped_column(String(255), server_default="")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class BlockedEmailPattern(Base):
    """Patterns regex d'emails interdits de connexion au gateway MCP."""

    __tablename__ = "blocked_email_patterns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pattern: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, server_default="")
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ─── Lifecycle ───────────────────────────────────────────────────


async def init_db():
    """Crée toutes les tables (dev only — en prod, utiliser Alembic)."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    await engine.dispose()
