"""MCP tools — Google Calendar (list_calendar_events, check_availability, create_calendar_event)."""

import json

from gateway.auth import get_current_user
from gateway.security.audit import audit
from gateway.security.policies import check_policies
from gateway.security.rate_limiter import rate_limiter


def register(mcp, calendar):
    @mcp.tool()
    async def list_calendar_events(start_date: str, end_date: str = "") -> str:
        """Lister les événements du calendrier Google pour une période donnée (format YYYY-MM-DD)."""
        user = get_current_user()
        if not end_date:
            end_date = start_date

        ok, msg, _ = await check_policies("list_calendar_events", user,
                                           {"start_date": start_date, "end_date": end_date})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="list_calendar_events")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="list_calendar_events", start=start_date, end=end_date)
        events = await calendar.list_events(start_date, end_date)
        await audit("TOOL_OK", user=user, tool="list_calendar_events", count=len(events))
        return json.dumps({
            "events": events, "count": len(events),
            "period": {"start": start_date, "end": end_date},
            "calendar_mode": calendar.mode,
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def check_availability(date: str, duration_minutes: int = 30) -> str:
        """Vérifier les créneaux disponibles pour une date donnée (format YYYY-MM-DD)."""
        user = get_current_user()

        ok, msg, _ = await check_policies("check_availability", user, {"date": date})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="check_availability")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="check_availability", date=date, duration=duration_minutes)
        slots = await calendar.check_availability(date, duration_minutes)
        await audit("TOOL_OK", user=user, tool="check_availability", slots=len(slots))
        return json.dumps({
            "date": date, "requested_duration_minutes": duration_minutes,
            "available_slots": slots, "calendar_mode": calendar.mode,
        }, ensure_ascii=False, indent=2)

    @mcp.tool()
    async def create_calendar_event(
        summary: str,
        start_datetime: str,
        end_datetime: str,
        description: str = "",
        location: str = "",
        attendees: str = "",
    ) -> str:
        """Créer un événement dans Google Calendar.
        - start_datetime / end_datetime : format ISO 8601 sans timezone (ex: 2026-04-08T14:00:00).
          Le fuseau horaire CALENDAR_TIMEZONE (Europe/Paris par défaut) est appliqué automatiquement.
        - attendees : emails séparés par des virgules (ex: alice@example.com,bob@example.com).
          Les invitations sont envoyées automatiquement.
        Conseil : appeler check_availability avant pour éviter les conflits."""
        user = get_current_user()

        ok, msg, _ = await check_policies("create_calendar_event", user, {"summary": summary, "attendees": attendees})
        if not ok:
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        ok, msg = await rate_limiter.check_action(user)
        if not ok:
            await audit("RATE_LIMITED", user=user, tool="create_calendar_event")
            return json.dumps({"blocked": True, "reason": msg}, ensure_ascii=False)

        await audit("TOOL_CALL", user=user, tool="create_calendar_event", summary=summary, start=start_datetime)

        attendees_list = [a.strip() for a in attendees.split(",") if a.strip()] if attendees else []
        result = await calendar.create_event(
            summary=summary,
            start_datetime=start_datetime,
            end_datetime=end_datetime,
            description=description,
            location=location,
            attendees=attendees_list,
        )

        if "error" not in result:
            await audit("CALENDAR_EVENT_CREATED", user=user, tool="create_calendar_event",
                        summary=summary, event_id=result.get("id", ""))

        return json.dumps(result, ensure_ascii=False, indent=2)
