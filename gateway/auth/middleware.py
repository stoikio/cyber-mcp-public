"""
Middleware d'authentification multi-méthode.
Ordre de priorité : Bearer JWT → X-API-Key → 401 (ou DEV_MODE fallback).
API keys lues depuis PostgreSQL avec cache in-memory.
Brute-force limité via Redis.
"""

import hashlib
import json
import time
from datetime import datetime, timezone

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse

from sqlalchemy import select

from gateway.config import DEV_MODE, HOST, USER_EMAIL, OAUTH_ISSUER, logger
from gateway.db import ApiKey, async_session
from gateway.auth import _current_user_email, is_email_blocked
from gateway.auth.jwt_utils import validate_jwt
from gateway.security.audit import audit
from gateway.security.rate_limiter import auth_failure_limiter

if DEV_MODE and HOST not in ("127.0.0.1", "localhost", "::1"):
    logger.critical(
        "SÉCURITÉ : DEV_MODE activé avec HOST=%s (non-localhost). "
        "Cela expose le gateway sans authentification sur le réseau. "
        "Utilisez HOST=127.0.0.1 ou désactivez DEV_MODE.",
        HOST,
    )

# ─── API Keys cache ──────────────────────────────────────────────

_API_KEYS_CACHE: dict[str, dict] = {}
_API_KEYS_CACHE_TS: float = 0.0
_API_KEYS_CACHE_TTL = 60  # seconds


async def _get_api_keys() -> dict[str, dict]:
    global _API_KEYS_CACHE, _API_KEYS_CACHE_TS

    if time.time() - _API_KEYS_CACHE_TS < _API_KEYS_CACHE_TTL and _API_KEYS_CACHE:
        return _API_KEYS_CACHE

    try:
        async with async_session() as session:
            result = await session.execute(
                select(ApiKey).where(ApiKey.revoked.is_(False))
            )
            rows = result.scalars().all()

        _API_KEYS_CACHE = {
            row.key_hash: {
                "email": row.email,
                "expires_at": row.expires_at.isoformat() if row.expires_at else "",
            }
            for row in rows
        }
        _API_KEYS_CACHE_TS = time.time()
        logger.debug("AUTH | API keys rechargées depuis PG : %d clé(s)", len(_API_KEYS_CACHE))
    except Exception as e:
        logger.warning("AUTH | Échec chargement API keys depuis PG : %s (cache conservé)", e)

    return _API_KEYS_CACHE


def _hash_api_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


# ─── OAuth paths exemptés ────────────────────────────────────────

_OAUTH_PATHS = frozenset({
    "/.well-known/oauth-authorization-server",
    "/.well-known/oauth-protected-resource",
    "/oauth/register",
    "/oauth/authorize",
    "/oauth/callback",
    "/oauth/token",
    "/health",
})


# ─── Middleware ──────────────────────────────────────────────────


class UserIdentMiddleware(BaseHTTPMiddleware):
    """Authentification multi-méthode par ordre de priorité :

    1. Authorization: Bearer <JWT> — flux OAuth2 (Claude Desktop)
    2. X-API-Key: <key>           — hash SHA-256 (Cursor, scripts, curl)
    3. Aucun header               — 401 en production, fallback USER_EMAIL en DEV_MODE
    """

    async def dispatch(self, request: StarletteRequest, call_next):
        path = request.url.path
        if path in _OAUTH_PATHS or path.startswith("/.well-known/oauth-protected-resource"):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"

        if await auth_failure_limiter.is_blocked(client_ip):
            await audit("AUTH_RATE_LIMITED", tool="middleware", ip=client_ip)
            return StarletteResponse(
                content=json.dumps(
                    {"error": "Trop de tentatives d'authentification. Réessayez dans 60 secondes."},
                    ensure_ascii=False,
                ),
                status_code=429,
                media_type="application/json",
            )

        token = _current_user_email.set("")
        try:
            return await self._authenticate_and_dispatch(request, call_next, client_ip)
        finally:
            _current_user_email.reset(token)

    async def _authenticate_and_dispatch(self, request, call_next, client_ip):
        # --- Method 1: Bearer JWT ---
        auth_header = request.headers.get("authorization", "")
        if auth_header.lower().startswith("bearer "):
            jwt_token = auth_header[7:].strip()
            email = validate_jwt(jwt_token)
            if email:
                if await is_email_blocked(email):
                    logger.warning("AUTH | Compte bloqué (JWT) : %s", email)
                    await audit("AUTH_BLOCKED_ACCOUNT", tool="middleware", user=email, method="bearer")
                    return StarletteResponse(
                        content=json.dumps(
                            {"error": "Ce compte n'est pas autorisé à accéder au gateway MCP."},
                            ensure_ascii=False,
                        ),
                        status_code=403,
                        media_type="application/json",
                    )
                _current_user_email.set(email)
                logger.debug("AUTH | JWT valide pour %s", email)
                return await call_next(request)
            await auth_failure_limiter.record_failure(client_ip)
            await audit("AUTH_FAILED", tool="middleware", ip=client_ip, method="bearer")
            return StarletteResponse(
                content=json.dumps(
                    {"error": "Token JWT invalide ou expiré"},
                    ensure_ascii=False,
                ),
                status_code=401,
                media_type="application/json",
            )

        # --- Method 2: X-API-Key ---
        api_key = request.headers.get("x-api-key", "").strip()

        if api_key:
            key_hash = _hash_api_key(api_key)
            api_keys = await _get_api_keys()
            key_data = api_keys.get(key_hash)

            if not key_data:
                await auth_failure_limiter.record_failure(client_ip)
                logger.warning("AUTH | Clé API invalide depuis %s", client_ip)
                await audit("AUTH_FAILED", tool="middleware", ip=client_ip, method="api_key")
                return StarletteResponse(
                    content=json.dumps(
                        {"error": "Clé API invalide ou inconnue"},
                        ensure_ascii=False,
                    ),
                    status_code=401,
                    media_type="application/json",
                )

            expires_at = key_data.get("expires_at", "")
            if expires_at:
                try:
                    exp = datetime.fromisoformat(expires_at)
                    if exp.tzinfo is None:
                        exp = exp.replace(tzinfo=timezone.utc)
                    if datetime.now(timezone.utc) > exp:
                        logger.warning("AUTH | Clé expirée pour %s", key_data.get("email", "?"))
                        await audit("AUTH_EXPIRED", tool="middleware", user=key_data.get("email", ""))
                        return StarletteResponse(
                            content=json.dumps(
                                {"error": "Clé API expirée. Contactez l'administrateur pour renouvellement."},
                                ensure_ascii=False,
                            ),
                            status_code=401,
                            media_type="application/json",
                        )
                except ValueError:
                    logger.error(
                        "AUTH | Format expires_at invalide pour %s — clé refusée (fail-closed)",
                        key_data.get("email", "?"),
                    )
                    return StarletteResponse(
                        content=json.dumps(
                            {"error": "Clé API avec date d'expiration invalide. Contactez l'administrateur."},
                            ensure_ascii=False,
                        ),
                        status_code=401,
                        media_type="application/json",
                    )

            if await is_email_blocked(key_data["email"]):
                logger.warning("AUTH | Compte bloqué (API key) : %s", key_data["email"])
                await audit("AUTH_BLOCKED_ACCOUNT", tool="middleware", user=key_data["email"], method="api_key")
                return StarletteResponse(
                    content=json.dumps(
                        {"error": "Ce compte n'est pas autorisé à accéder au gateway MCP."},
                        ensure_ascii=False,
                    ),
                    status_code=403,
                    media_type="application/json",
                )
            _current_user_email.set(key_data["email"])
            logger.debug("AUTH | Utilisateur identifié (API key) : %s", key_data["email"])
            return await call_next(request)

        # --- Method 3: No credentials ---
        if DEV_MODE:
            _current_user_email.set(USER_EMAIL)
            logger.debug("AUTH | DEV_MODE actif — fallback USER_EMAIL=%s", USER_EMAIL)
            return await call_next(request)

        resource_metadata_url = f"{OAUTH_ISSUER}/.well-known/oauth-protected-resource"
        return StarletteResponse(
            content=json.dumps(
                {"error": "Authentification requise (Bearer JWT ou X-API-Key)"},
                ensure_ascii=False,
            ),
            status_code=401,
            media_type="application/json",
            headers={
                "WWW-Authenticate": f'Bearer resource_metadata="{resource_metadata_url}"',
            },
        )
