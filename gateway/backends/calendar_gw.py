"""Backend Google Calendar — API OAuth2 avec résolution per-user."""

from datetime import datetime
from typing import Any

from gateway.config import CALENDAR_TIMEZONE, GOOGLE_CLIENT_ID, logger
from gateway.auth import get_current_user
from gateway.backends.token_store import user_token_store

_MULTI_TENANT = bool(GOOGLE_CLIENT_ID)


class CalendarBackend:
    """Backend Google Calendar.
    Résolution du service par utilisateur (tokens OAuth2 per-user stockés en PG).
    GOOGLE_CLIENT_ID doit être configuré pour le mode multi-tenant.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]

    def __init__(self):
        if not _MULTI_TENANT:
            logger.warning(
                "CALENDAR | GOOGLE_CLIENT_ID non configuré — mode mock. "
                "Configurez OAuth2 pour activer Google Calendar."
            )

    async def _get_user_service(self):
        email = get_current_user()
        creds = await user_token_store.get_credentials(email, self.SCOPES)
        if creds:
            from googleapiclient.discovery import build
            return build("calendar", "v3", credentials=creds)
        return None

    @property
    def mode(self) -> str:
        return "oauth" if _MULTI_TENANT else "mock"

    async def list_events(self, start_date: str, end_date: str) -> list[dict]:
        service = await self._get_user_service()
        if not service:
            return self._mock_events(start_date)

        try:
            y0, m0, d0 = map(int, start_date.split("-"))
            y1, m1, d1 = map(int, end_date.split("-"))
            time_min = datetime(y0, m0, d0, 0, 0, 0).astimezone().isoformat()
            time_max = datetime(y1, m1, d1, 23, 59, 59).astimezone().isoformat()

            response = service.events().list(
                calendarId="primary",
                timeMin=time_min, timeMax=time_max,
                singleEvents=True, orderBy="startTime", maxResults=50
            ).execute()
            events = response.get("items", [])
            return [{
                "id": e.get("id", ""),
                "summary": e.get("summary", "(sans titre)"),
                "start": e.get("start", {}).get("dateTime", e.get("start", {}).get("date", "")),
                "end": e.get("end", {}).get("dateTime", e.get("end", {}).get("date", "")),
                "location": e.get("location", ""),
                "description": e.get("description", ""),
                "hangout_link": e.get("hangoutLink", ""),
                "organizer": e.get("organizer", {}).get("email", ""),
                "status": e.get("status", ""),
                "attendees": [
                    {"email": a.get("email", ""), "response": a.get("responseStatus", "")}
                    for a in e.get("attendees", [])
                ],
            } for e in events]

        except Exception as e:
            logger.error("CALENDAR_LIST | Erreur : %s", str(e))
            return [{"error": "Erreur lors de la récupération des événements. Réessayez ultérieurement."}]

    async def check_availability(self, date: str, duration_minutes: int) -> list[dict]:
        events = await self.list_events(date, date)
        if events and "error" in events[0]:
            return events

        busy = []
        for e in events:
            start_str = e.get("start", "")
            end_str = e.get("end", "")
            if "T" in start_str:
                try:
                    s_dt = datetime.fromisoformat(start_str).astimezone()
                    e_dt = datetime.fromisoformat(end_str).astimezone()
                    busy.append((s_dt.hour * 60 + s_dt.minute, e_dt.hour * 60 + e_dt.minute))
                except (ValueError, AttributeError):
                    pass

        busy.sort()
        free = []
        current = 9 * 60
        end_of_day = 18 * 60

        for start, end in busy:
            if start > current and (start - current) >= duration_minutes:
                free.append({
                    "start": f"{date}T{current // 60:02d}:{current % 60:02d}:00",
                    "end": f"{date}T{start // 60:02d}:{start % 60:02d}:00",
                })
            current = max(current, end)

        if end_of_day > current and (end_of_day - current) >= duration_minutes:
            free.append({
                "start": f"{date}T{current // 60:02d}:{current % 60:02d}:00",
                "end": f"{date}T{end_of_day // 60:02d}:{end_of_day % 60:02d}:00",
            })

        return free

    async def create_event(
        self,
        summary: str,
        start_datetime: str,
        end_datetime: str,
        description: str = "",
        location: str = "",
        attendees: list[str] | None = None,
    ) -> dict:
        service = await self._get_user_service()
        if not service:
            return self._mock_created_event(summary, start_datetime, end_datetime)

        try:
            event_body: dict[str, Any] = {
                "summary": summary,
                "start": {"dateTime": start_datetime, "timeZone": CALENDAR_TIMEZONE},
                "end": {"dateTime": end_datetime, "timeZone": CALENDAR_TIMEZONE},
            }
            if description:
                event_body["description"] = description
            if location:
                event_body["location"] = location
            if attendees:
                event_body["attendees"] = [{"email": a} for a in attendees]

            result = service.events().insert(
                calendarId="primary", body=event_body, sendUpdates="all",
            ).execute()

            return {
                "id": result.get("id", ""),
                "summary": result.get("summary", ""),
                "start": result.get("start", {}).get("dateTime", ""),
                "end": result.get("end", {}).get("dateTime", ""),
                "html_link": result.get("htmlLink", ""),
                "status": result.get("status", ""),
            }
        except Exception as e:
            logger.error("CALENDAR_CREATE | Erreur : %s", str(e))
            return {"error": "Erreur lors de la création de l'événement. Réessayez ultérieurement."}

    def _mock_created_event(self, summary: str, start_datetime: str, end_datetime: str) -> dict:
        return {
            "id": "mock-evt-new", "summary": summary,
            "start": start_datetime, "end": end_datetime,
            "html_link": "https://calendar.google.com/calendar/event?eid=mock",
            "status": "confirmed", "mock": True,
        }

    def _mock_events(self, start_date: str) -> list[dict]:
        return [
            {"id": "evt-1", "summary": "Stand-up équipe", "start": f"{start_date}T09:00:00",
             "end": f"{start_date}T09:30:00", "location": "Google Meet", "attendees": [],
             "description": "", "hangout_link": "", "organizer": "", "status": "confirmed"},
            {"id": "evt-2", "summary": "Review architecture", "start": f"{start_date}T14:00:00",
             "end": f"{start_date}T15:00:00", "location": "Salle B", "attendees": [],
             "description": "", "hangout_link": "", "organizer": "", "status": "confirmed"},
            {"id": "evt-3", "summary": "1:1 avec CEO", "start": f"{start_date}T16:00:00",
             "end": f"{start_date}T16:30:00", "location": "Bureau CEO", "attendees": [],
             "description": "", "hangout_link": "", "organizer": "", "status": "confirmed"},
        ]
