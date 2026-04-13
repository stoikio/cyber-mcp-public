"""Backend Gmail — API Google OAuth2 avec résolution per-user."""

import base64
import json
import re
import time
from email.mime.text import MIMEText
from typing import Any

from gateway.config import GOOGLE_CLIENT_ID, logger
from gateway.auth import get_current_user
from gateway.backends.token_store import user_token_store

_MULTI_TENANT = bool(GOOGLE_CLIENT_ID)


class GmailBackend:
    """Backend Gmail utilisant l'API Google avec OAuth2.
    Résolution du service par utilisateur (tokens OAuth2 per-user stockés en PG).
    GOOGLE_CLIENT_ID doit être configuré pour le mode multi-tenant.
    """

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
    ]

    def __init__(self):
        if not _MULTI_TENANT:
            logger.warning(
                "GMAIL | GOOGLE_CLIENT_ID non configuré — mode mock. "
                "Configurez OAuth2 pour activer Gmail."
            )

    async def _get_user_service(self):
        email = get_current_user()
        creds = await user_token_store.get_credentials(email, self.SCOPES)
        if creds:
            from googleapiclient.discovery import build
            return build("gmail", "v1", credentials=creds)
        return None

    @property
    def mode(self) -> str:
        return "oauth" if _MULTI_TENANT else "mock"

    def _get_header(self, headers: list[dict], name: str) -> str:
        for h in headers:
            if h.get("name", "").lower() == name.lower():
                return h.get("value", "")
        return ""

    def _extract_body(self, payload: dict) -> str:
        if payload.get("body", {}).get("data"):
            return base64.urlsafe_b64decode(payload["body"]["data"]).decode("utf-8", errors="replace")

        parts = payload.get("parts", [])
        for part in parts:
            mime = part.get("mimeType", "")
            if mime == "text/plain" and part.get("body", {}).get("data"):
                return base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
        for part in parts:
            mime = part.get("mimeType", "")
            if mime == "text/html" and part.get("body", {}).get("data"):
                html = base64.urlsafe_b64decode(part["body"]["data"]).decode("utf-8", errors="replace")
                return re.sub(r'<[^>]+>', '', html)
        for part in parts:
            if part.get("parts"):
                result = self._extract_body(part)
                if result:
                    return result
        return ""

    def _format_message(self, msg: dict, include_body: bool = False) -> dict:
        payload = msg.get("payload", {})
        headers = payload.get("headers", [])

        result = {
            "id": msg.get("id", ""),
            "threadId": msg.get("threadId", ""),
            "from": self._get_header(headers, "From"),
            "to": self._get_header(headers, "To"),
            "cc": self._get_header(headers, "Cc"),
            "subject": self._get_header(headers, "Subject"),
            "date": self._get_header(headers, "Date"),
            "message_id": self._get_header(headers, "Message-ID"),
            "snippet": msg.get("snippet", ""),
            "labels": msg.get("labelIds", []),
        }
        if include_body:
            result["body"] = self._extract_body(payload)
        return result

    async def list_messages(self, query: str = "", max_results: int = 10) -> list[dict]:
        service = await self._get_user_service()
        if not service:
            return self._mock_messages(query, max_results)
        try:
            params: dict[str, Any] = {"userId": "me", "maxResults": max_results}
            if query:
                params["q"] = query
            response = service.users().messages().list(**params).execute()
            messages = response.get("messages", [])
            result = []
            for msg_ref in messages:
                msg = service.users().messages().get(userId="me", id=msg_ref["id"], format="full").execute()
                result.append(self._format_message(msg))
            return result
        except Exception as e:
            logger.error("GMAIL_LIST | Erreur : %s", str(e))
            return [{"error": "Erreur lors de la récupération des emails. Réessayez ultérieurement."}]

    async def get_message(self, message_id: str) -> dict:
        service = await self._get_user_service()
        if not service:
            return self._mock_single_message(message_id)
        try:
            msg = service.users().messages().get(userId="me", id=message_id, format="full").execute()
            return self._format_message(msg, include_body=True)
        except Exception as e:
            logger.error("GMAIL_GET | Erreur : %s", str(e))
            return {"error": "Erreur lors de la lecture de l'email. Réessayez ultérieurement."}

    @staticmethod
    def _sanitize_header(value: str) -> str:
        """Supprime les caractères CRLF pour éviter l'injection de headers MIME."""
        return value.replace("\r", "").replace("\n", "")

    async def send_message(self, to: str, subject: str, body: str) -> dict:
        service = await self._get_user_service()
        if not service:
            logger.info("MOCK_SEND | envoi simulé")
            return {"status": "sent", "id": f"mock-{int(time.time())}", "to": to,
                    "note": "[MOCK] Gmail non configuré. Connectez-vous via OAuth."}
        try:
            message = MIMEText(body)
            message["to"] = self._sanitize_header(to)
            message["subject"] = self._sanitize_header(subject)
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            result = service.users().messages().send(userId="me", body={"raw": raw}).execute()
            return {"status": "sent", "id": result.get("id", ""), "to": to}
        except Exception as e:
            logger.error("GMAIL_SEND | Erreur : %s", str(e))
            return {"error": "Erreur lors de l'envoi de l'email. Réessayez ultérieurement."}

    async def create_draft(self, to: str, subject: str, body: str,
                           thread_id: str = "", in_reply_to: str = "", cc: str = "") -> dict:
        service = await self._get_user_service()
        if not service:
            logger.info("MOCK_DRAFT | brouillon simulé")
            return {"status": "draft_created", "id": f"draft-{int(time.time())}", "to": to,
                    "note": "[MOCK] Gmail non configuré. Connectez-vous via OAuth."}
        try:
            message = MIMEText(body)
            message["to"] = self._sanitize_header(to)
            if cc:
                message["cc"] = self._sanitize_header(cc)
            message["subject"] = self._sanitize_header(subject)
            if in_reply_to:
                sanitized_reply = self._sanitize_header(in_reply_to)
                message["In-Reply-To"] = sanitized_reply
                message["References"] = sanitized_reply
            raw = base64.urlsafe_b64encode(message.as_bytes()).decode("utf-8")
            draft_body: dict[str, Any] = {"message": {"raw": raw}}
            if thread_id:
                draft_body["message"]["threadId"] = thread_id
            result = service.users().drafts().create(userId="me", body=draft_body).execute()
            return {"status": "draft_created", "id": result.get("id", ""),
                    "to": to, "cc": cc, "thread_id": thread_id}
        except Exception as e:
            logger.error("GMAIL_DRAFT | Erreur : %s", str(e))
            return {"error": "Erreur lors de la création du brouillon. Réessayez ultérieurement."}

    # ── Mock fallback ──

    def _mock_messages(self, query: str, max_results: int) -> list[dict]:
        mocks = [
            {"id": "msg-001", "from": "alice@example.com", "subject": "Réunion Q2 planning",
             "snippet": "Bonjour, pourrions-nous décaler la réunion de mardi à jeudi ?",
             "date": "2026-04-03T09:15:00Z", "labels": ["INBOX"]},
            {"id": "msg-002", "from": "bob@partner.com", "subject": "Partnership proposal",
             "snippet": "Suite à notre échange, veuillez trouver ci-joint notre proposition...",
             "date": "2026-04-03T08:30:00Z", "labels": ["INBOX"]},
            {"id": "msg-003", "from": "noreply@accounts.google.com", "subject": "Reset your password",
             "snippet": "Click here to reset your password. Code: 847291",
             "date": "2026-04-03T07:00:00Z", "labels": ["INBOX"]},
            {"id": "msg-004", "from": "cto@bigclient.com", "subject": "URGENT - Incident de sécurité signalé",
             "snippet": "Nous avons détecté une activité anormale sur notre police cyber...",
             "date": "2026-04-03T06:45:00Z", "labels": ["INBOX", "IMPORTANT"]},
            {"id": "msg-005", "from": "newsletter@techdigest.io", "subject": "Weekly Tech Digest #142",
             "snippet": "This week in AI: new developments in agent security...",
             "date": "2026-04-02T18:00:00Z", "labels": ["INBOX", "CATEGORY_PROMOTIONS"]},
        ]
        if query:
            q = query.lower()
            mocks = [m for m in mocks if q in m["subject"].lower() or q in m["from"].lower() or q in m["snippet"].lower()]
        return mocks[:max_results]

    def _mock_single_message(self, message_id: str) -> dict:
        for m in self._mock_messages("", 100):
            if m["id"] == message_id:
                m["body"] = m["snippet"] + "\n\nCordialement,\n" + m["from"].split("@")[0]
                return m
        return {"error": f"Message {message_id} non trouvé"}
