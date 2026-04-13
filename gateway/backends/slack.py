"""Backend Slack — slack-sdk avec fallback mock."""

import os
from datetime import datetime, timezone

from sqlalchemy import select

from gateway.config import logger


class SlackBackend:
    """Backend Slack utilisant slack-sdk.
    Token résolu dans l'ordre : variable d'env SLACK_BOT_TOKEN → PostgreSQL
    (integration_tokens via reload_from_db) → mode mock.
    """

    def __init__(self):
        self.client = None
        self.mode = "mock"
        self._init_client()

    def _init_client(self):
        token = os.getenv("SLACK_BOT_TOKEN", "")
        if not token:
            logger.info("SLACK | SLACK_BOT_TOKEN non défini — en attente du chargement depuis la DB.")
            return

        self._connect(token)

    def _connect(self, token: str):
        """Initialise le client Slack avec un token donné."""
        try:
            from slack_sdk import WebClient
            self.client = WebClient(token=token)
            auth = self.client.auth_test()
            logger.info("SLACK | Connecté en tant que '%s' dans le workspace '%s'",
                       auth.get("user", "?"), auth.get("team", "?"))
            self.mode = "real"
        except Exception as e:
            logger.error("SLACK | Erreur d'initialisation : %s. Mode MOCK actif.", str(e))

    async def reload_from_db(self):
        """Recharge le token depuis la DB (appelé au startup après init_db)."""
        from gateway.backends.integration_store import get_token
        token = await get_token("slack")
        if token:
            self._connect(token)
            if self.mode == "real":
                logger.info("SLACK | Token rechargé depuis la base de données")

    async def send_message(self, channel: str, text: str) -> dict:
        if self.mode == "mock":
            return {"status": "sent", "channel": channel,
                    "note": "[MOCK] Slack non configuré. Définissez SLACK_BOT_TOKEN."}

        allowed = await self.get_allowed_channels()
        channel_norm = channel.lstrip("#")
        matched = next(
            (c for c in allowed
             if c["channel_id"] == channel_norm or c["channel_name"] == channel_norm),
            None,
        )
        if not matched:
            return {"error": f"Canal '{channel}' non autorisé. "
                    "Seuls les canaux configurés par l'administrateur sont accessibles en écriture."}

        try:
            response = self.client.chat_postMessage(channel=matched["channel_id"], text=text)
            return {"status": "sent", "channel": matched["channel_name"], "ts": response.get("ts", "")}
        except Exception as e:
            logger.error("SLACK_SEND | Erreur envoi canal %s", matched["channel_name"])
            return {"error": "Échec de l'envoi du message Slack. Réessayez ultérieurement."}

    async def send_dm(self, user: str, text: str) -> dict:
        if self.mode == "mock":
            return {"status": "sent", "user": user,
                    "note": "[MOCK] Slack non configuré. Définissez SLACK_BOT_TOKEN."}
        try:
            user_id = user
            if not user.startswith("U"):
                users = self.client.users_list()
                for u in users.get("members", []):
                    if u.get("name") == user or u.get("real_name", "").lower() == user.lower():
                        user_id = u["id"]
                        break
            conv = self.client.conversations_open(users=[user_id])
            channel_id = conv["channel"]["id"]
            response = self.client.chat_postMessage(channel=channel_id, text=text)
            return {"status": "sent", "user": user, "ts": response.get("ts", "")}
        except Exception as e:
            logger.error("SLACK_DM | Erreur envoi DM à %s", user)
            return {"error": "Échec de l'envoi du message direct Slack. Réessayez ultérieurement."}

    async def get_allowed_channels(self) -> list[dict]:
        """Retourne la liste des canaux Slack autorisés (depuis PG)."""
        from gateway.db import SlackChannel, async_session

        async with async_session() as session:
            rows = (
                await session.execute(
                    select(SlackChannel).where(SlackChannel.enabled.is_(True))
                    .order_by(SlackChannel.channel_name)
                )
            ).scalars().all()
        return [
            {"channel_id": r.channel_id, "channel_name": r.channel_name,
             "description": r.description, "max_messages": r.max_messages}
            for r in rows
        ]

    async def read_channel(self, channel: str, limit: int = 20) -> dict:
        """Lit les derniers messages d'un canal Slack autorisé."""
        from gateway.db import SlackChannel, async_session

        async with async_session() as session:
            row = (
                await session.execute(
                    select(SlackChannel).where(
                        SlackChannel.enabled.is_(True),
                        (SlackChannel.channel_id == channel) | (SlackChannel.channel_name == channel.lstrip("#")),
                    )
                )
            ).scalar_one_or_none()

        if not row:
            return {"error": f"Canal '{channel}' non autorisé ou inexistant. "
                    "Utilisez list_slack_channels pour voir les canaux disponibles."}

        effective_limit = min(limit, row.max_messages)

        if self.mode == "mock":
            return {
                "channel": row.channel_name,
                "channel_id": row.channel_id,
                "messages": [
                    {"user": "mock-user", "text": f"[MOCK] Message de test #{i+1}",
                     "ts": "1700000000.000000"}
                    for i in range(min(effective_limit, 3))
                ],
                "count": min(effective_limit, 3),
                "note": "[MOCK] Slack non configuré. Définissez SLACK_BOT_TOKEN.",
            }

        try:
            response = self.client.conversations_history(
                channel=row.channel_id, limit=effective_limit
            )
            messages = []
            for msg in response.get("messages", []):
                ts_float = float(msg.get("ts", "0"))
                messages.append({
                    "user": msg.get("user", "unknown"),
                    "text": msg.get("text", ""),
                    "ts": msg.get("ts", ""),
                    "datetime": datetime.fromtimestamp(ts_float, tz=timezone.utc).isoformat(),
                })
            messages.reverse()
            return {
                "channel": row.channel_name,
                "channel_id": row.channel_id,
                "messages": messages,
                "count": len(messages),
            }
        except Exception as e:
            logger.error("SLACK_READ | Erreur lecture canal %s : %s", channel, str(e))
            return {"error": "Erreur lors de la lecture du canal Slack. Réessayez ultérieurement."}
