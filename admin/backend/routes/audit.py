"""Audit log query endpoint with filtering and pagination."""

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from gateway.db import AuditEvent, async_session

from admin.backend.auth import get_admin_user
from admin.backend.schemas import AuditEventOut, AuditPage

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("", response_model=AuditPage)
async def list_audit_events(
    event: str | None = Query(None, description="Filter by event type"),
    user_email: str | None = Query(None, description="Filter by user email (contains)"),
    tool: str | None = Query(None, description="Filter by tool name"),
    date_from: datetime | None = Query(None, description="Start date (ISO 8601)"),
    date_to: datetime | None = Query(None, description="End date (ISO 8601)"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: str = Depends(get_admin_user),
):
    base = select(AuditEvent)
    count_q = select(func.count(AuditEvent.id))

    if event:
        base = base.where(AuditEvent.event == event)
        count_q = count_q.where(AuditEvent.event == event)
    if user_email:
        pattern = f"%{user_email}%"
        base = base.where(AuditEvent.user_email.ilike(pattern))
        count_q = count_q.where(AuditEvent.user_email.ilike(pattern))
    if tool:
        base = base.where(AuditEvent.tool == tool)
        count_q = count_q.where(AuditEvent.tool == tool)
    if date_from:
        base = base.where(AuditEvent.ts >= date_from)
        count_q = count_q.where(AuditEvent.ts >= date_from)
    if date_to:
        base = base.where(AuditEvent.ts <= date_to)
        count_q = count_q.where(AuditEvent.ts <= date_to)

    async with async_session() as session:
        total = (await session.execute(count_q)).scalar_one()
        rows = (
            await session.execute(
                base.order_by(AuditEvent.ts.desc())
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()

    return AuditPage(
        items=[AuditEventOut.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )
