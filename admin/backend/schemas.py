"""Pydantic request/response models for the admin API."""

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


# ─── Auth ─────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    api_key: str = Field(..., min_length=1)


class LoginResponse(BaseModel):
    token: str
    email: str
    expires_in: int = 7200


# ─── Policies ─────────────────────────────────────────────────────

class PolicyBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    description: str = ""
    tool_pattern: str = Field(default="*", max_length=128)
    action: str = Field(default="block", pattern=r"^(block|warn|log)$")
    conditions: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    priority: int = 0


class PolicyCreate(PolicyBase):
    pass


class PolicyUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    tool_pattern: str | None = Field(default=None, max_length=128)
    action: str | None = Field(default=None, pattern=r"^(block|warn|log)$")
    conditions: dict[str, Any] | None = None
    enabled: bool | None = None
    priority: int | None = None


class PolicyOut(PolicyBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── API Keys ─────────────────────────────────────────────────────

class ApiKeyCreate(BaseModel):
    email: str = Field(..., min_length=1, max_length=255)
    expires_in_days: int = Field(default=180, ge=1, le=730)


class ApiKeyCreated(BaseModel):
    api_key: str
    hash_prefix: str
    email: str
    expires_at: datetime | None


class ApiKeyOut(BaseModel):
    hash_prefix: str
    email: str
    created_at: datetime
    expires_at: datetime | None
    revoked: bool

    model_config = {"from_attributes": True}


# ─── Audit ────────────────────────────────────────────────────────

class AuditEventOut(BaseModel):
    id: int
    ts: datetime
    event: str
    user_email: str
    tool: str
    details: dict[str, Any]
    ip: str

    model_config = {"from_attributes": True}


class AuditPage(BaseModel):
    items: list[AuditEventOut]
    total: int
    limit: int
    offset: int


# ─── OAuth Clients ────────────────────────────────────────────────

class OAuthClientOut(BaseModel):
    client_id: str
    client_name: str
    redirect_uris: list[str] | Any
    grant_types: list[str] | Any
    created_at: datetime

    model_config = {"from_attributes": True}


# ─── Integration Tokens ──────────────────────────────────────────

class IntegrationTokenUpdate(BaseModel):
    value: str = Field(..., min_length=1)
    label: str = ""


class IntegrationTokenOut(BaseModel):
    service: str
    label: str
    masked_value: str
    updated_by: str
    created_at: datetime | None = None
    updated_at: datetime | None = None


class IntegrationStatusOut(BaseModel):
    service: str
    name: str
    description: str
    configured: bool
    mode: str
    masked_value: str
    label: str
    updated_by: str
    updated_at: datetime | None = None


# ─── Slack Channels ───────────────────────────────────────────────

class SlackChannelBase(BaseModel):
    channel_id: str = Field(..., min_length=1, max_length=32)
    channel_name: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    enabled: bool = True
    max_messages: int = Field(default=50, ge=1, le=500)


class SlackChannelCreate(SlackChannelBase):
    pass


class SlackChannelUpdate(BaseModel):
    channel_id: str | None = Field(default=None, min_length=1, max_length=32)
    channel_name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    enabled: bool | None = None
    max_messages: int | None = Field(default=None, ge=1, le=500)


class SlackChannelOut(SlackChannelBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Stats ────────────────────────────────────────────────────────

class EventCount(BaseModel):
    event: str
    count: int


class DailyCount(BaseModel):
    date: str
    count: int


class TopUser(BaseModel):
    email: str
    count: int


# ─── Blocked Email Patterns ───────────────────────────────────────

class BlockedEmailPatternBase(BaseModel):
    pattern: str = Field(..., min_length=1, max_length=255)
    description: str = ""
    enabled: bool = True


class BlockedEmailPatternCreate(BlockedEmailPatternBase):
    pass


class BlockedEmailPatternUpdate(BaseModel):
    pattern: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    enabled: bool | None = None


class BlockedEmailPatternOut(BlockedEmailPatternBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ─── Stats ────────────────────────────────────────────────────────

class StatsOut(BaseModel):
    total_events: int
    total_blocked: int
    total_rate_limited: int
    active_users: int
    active_policies: int
    active_api_keys: int
    events_by_type: list[EventCount]
    events_by_day: list[DailyCount]
    top_users: list[TopUser]
    recent_events: list[AuditEventOut]
