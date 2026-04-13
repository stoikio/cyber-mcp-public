"""
UserTokenStore — stocke les tokens Google OAuth2 par utilisateur en PostgreSQL.
Les données sont chiffrées avec Fernet avant stockage (colonne encrypted_token_data).
"""

import asyncio
import json
from datetime import datetime, timezone

from sqlalchemy import select, func

from gateway.config import GOOGLE_TOKEN_URL, logger
from gateway.crypto import encrypt_data, decrypt_data
from gateway.db import UserToken, async_session


class UserTokenStore:
    """Stocke et récupère les tokens Google OAuth2 par utilisateur (PG + Fernet)."""

    def __init__(self):
        self._refresh_locks: dict[str, asyncio.Lock] = {}

    def _get_lock(self, email: str) -> asyncio.Lock:
        if email not in self._refresh_locks:
            self._refresh_locks[email] = asyncio.Lock()
        return self._refresh_locks[email]

    async def save(self, email: str, google_token_response: dict):
        """Persiste les tokens Google d'un utilisateur.

        Si l'utilisateur a déjà un refresh_token stocké et que Google n'en
        renvoie pas (re-auth sans prompt=consent), on conserve l'ancien.
        """
        from gateway.config import GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET

        cred_data = {
            "token": google_token_response.get("access_token", ""),
            "refresh_token": google_token_response.get("refresh_token", ""),
            "token_uri": GOOGLE_TOKEN_URL,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "scopes": google_token_response.get("scope", "").split(),
        }

        if not cred_data["refresh_token"]:
            existing = await self._load_raw(email)
            if existing:
                cred_data["refresh_token"] = existing.get("refresh_token", "")

        encrypted = encrypt_data(json.dumps(cred_data))

        async with async_session() as session:
            existing_row = await session.get(UserToken, email)
            if existing_row:
                existing_row.encrypted_token_data = encrypted
                existing_row.scopes = cred_data["scopes"]
                existing_row.last_refreshed_at = datetime.now(timezone.utc)
            else:
                row = UserToken(
                    email=email,
                    encrypted_token_data=encrypted,
                    scopes=cred_data["scopes"],
                )
                session.add(row)
            await session.commit()

        logger.info("USER_TOKENS | Tokens Google sauvegardés pour %s", email)

    async def _load_raw(self, email: str) -> dict | None:
        """Charge et déchiffre les token data brutes."""
        async with async_session() as session:
            row = await session.get(UserToken, email)
        if not row:
            return None
        try:
            return json.loads(decrypt_data(row.encrypted_token_data))
        except Exception:
            return None

    async def get_credentials(self, email: str, scopes: list[str]):
        """Charge les credentials Google d'un utilisateur.

        Retourne un objet google.oauth2.credentials.Credentials ou None.
        Utilise un lock par utilisateur pour éviter les refresh concurrents.
        """
        lock = self._get_lock(email)
        async with lock:
            return await self._get_credentials_locked(email, scopes)

    async def _get_credentials_locked(self, email: str, scopes: list[str]):
        raw = await self._load_raw(email)
        if not raw:
            return None

        try:
            from google.oauth2.credentials import Credentials
            from google.auth.transport.requests import Request

            creds = Credentials.from_authorized_user_info(raw, scopes)

            if creds.expired and creds.refresh_token:
                await asyncio.to_thread(creds.refresh, Request())
                await self._save_refreshed_token(email, creds, raw)

            return creds
        except Exception as e:
            logger.warning("USER_TOKENS | Erreur chargement tokens pour %s : %s", email, e)
            return None

    async def _save_refreshed_token(self, email: str, creds, raw: dict):
        """Met à jour le token après refresh."""
        raw["token"] = creds.token
        encrypted = encrypt_data(json.dumps(raw))
        async with async_session() as session:
            row = await session.get(UserToken, email)
            if row:
                row.encrypted_token_data = encrypted
                row.last_refreshed_at = datetime.now(timezone.utc)
                await session.commit()
        logger.debug("USER_TOKENS | Token rafraîchi pour %s", email)

    async def count(self) -> int:
        async with async_session() as session:
            result = await session.execute(select(func.count()).select_from(UserToken))
            return result.scalar_one()


user_token_store = UserTokenStore()
