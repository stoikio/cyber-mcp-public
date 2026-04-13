"""Dashboard statistics endpoint."""

from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text

from gateway.db import AuditEvent, Policy, ApiKey, async_session

from admin.backend.auth import get_admin_user
from admin.backend.schemas import (
    AuditEventOut,
    DailyCount,
    EventCount,
    StatsOut,
    TopUser,
)

router = APIRouter(prefix="/api", tags=["stats"])


@router.get("/stats", response_model=StatsOut)
async def get_stats(_admin: str = Depends(get_admin_user)):
    now = datetime.now(timezone.utc)
    seven_days_ago = now - timedelta(days=7)

    async with async_session() as session:
        total_events = (
            await session.execute(select(func.count(AuditEvent.id)))
        ).scalar_one()

        total_blocked = (
            await session.execute(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.event.in_(["BLOCKED", "POLICY_BLOCKED"])
                )
            )
        ).scalar_one()

        total_rate_limited = (
            await session.execute(
                select(func.count(AuditEvent.id)).where(
                    AuditEvent.event == "RATE_LIMITED"
                )
            )
        ).scalar_one()

        active_users = (
            await session.execute(
                select(func.count(func.distinct(AuditEvent.user_email))).where(
                    AuditEvent.ts >= seven_days_ago,
                    AuditEvent.user_email != "",
                )
            )
        ).scalar_one()

        active_policies = (
            await session.execute(
                select(func.count(Policy.id)).where(Policy.enabled.is_(True))
            )
        ).scalar_one()

        active_api_keys = (
            await session.execute(
                select(func.count(ApiKey.key_hash)).where(
                    ApiKey.revoked.is_(False)
                )
            )
        ).scalar_one()

        events_by_type_rows = (
            await session.execute(
                select(AuditEvent.event, func.count(AuditEvent.id).label("cnt"))
                .group_by(AuditEvent.event)
                .order_by(text("cnt DESC"))
                .limit(15)
            )
        ).all()

        events_by_day_rows = (
            await session.execute(
                select(
                    func.date_trunc("day", AuditEvent.ts).label("day"),
                    func.count(AuditEvent.id).label("cnt"),
                )
                .where(AuditEvent.ts >= seven_days_ago)
                .group_by(text("day"))
                .order_by(text("day"))
            )
        ).all()

        top_users_rows = (
            await session.execute(
                select(
                    AuditEvent.user_email,
                    func.count(AuditEvent.id).label("cnt"),
                )
                .where(AuditEvent.ts >= seven_days_ago, AuditEvent.user_email != "")
                .group_by(AuditEvent.user_email)
                .order_by(text("cnt DESC"))
                .limit(10)
            )
        ).all()

        recent_rows = (
            await session.execute(
                select(AuditEvent)
                .order_by(AuditEvent.ts.desc())
                .limit(20)
            )
        ).scalars().all()

    return StatsOut(
        total_events=total_events,
        total_blocked=total_blocked,
        total_rate_limited=total_rate_limited,
        active_users=active_users,
        active_policies=active_policies,
        active_api_keys=active_api_keys,
        events_by_type=[
            EventCount(event=r[0], count=r[1]) for r in events_by_type_rows
        ],
        events_by_day=[
            DailyCount(date=r[0].strftime("%Y-%m-%d"), count=r[1])
            for r in events_by_day_rows
        ],
        top_users=[TopUser(email=r[0], count=r[1]) for r in top_users_rows],
        recent_events=[AuditEventOut.model_validate(r) for r in recent_rows],
    )
