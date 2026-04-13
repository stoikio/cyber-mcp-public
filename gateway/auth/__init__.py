"""Auth layer — JWT, middleware, OAuth2."""

import re
import time
from contextvars import ContextVar

from sqlalchemy import select

from gateway.config import DEV_MODE, GOOGLE_CLIENT_ID, USER_EMAIL

_current_user_email: ContextVar[str] = ContextVar("current_user_email", default="")

_MULTI_TENANT = bool(GOOGLE_CLIENT_ID)

# ─── Blocked email patterns (loaded from PostgreSQL, cached 60s) ─

_blocked_cache: list[re.Pattern] = []
_blocked_cache_ts: float = 0.0
_BLOCKED_CACHE_TTL = 60


async def _load_blocked_patterns() -> list[re.Pattern]:
    """Charge les patterns bloqués depuis PG avec cache in-memory."""
    global _blocked_cache, _blocked_cache_ts

    now = time.time()
    if now - _blocked_cache_ts < _BLOCKED_CACHE_TTL and _blocked_cache is not None:
        return _blocked_cache

    try:
        from gateway.db import BlockedEmailPattern, async_session
        async with async_session() as session:
            rows = (
                await session.execute(
                    select(BlockedEmailPattern.pattern)
                    .where(BlockedEmailPattern.enabled.is_(True))
                )
            ).scalars().all()
        _blocked_cache = [re.compile(p, re.IGNORECASE) for p in rows]
        _blocked_cache_ts = now
    except Exception:
        pass

    return _blocked_cache


async def is_email_blocked(email: str) -> bool:
    """Vérifie si l'email correspond à un pattern interdit (ex: comptes admin/service)."""
    patterns = await _load_blocked_patterns()
    return any(rx.search(email) for rx in patterns)


def get_current_user() -> str:
    """Retourne l'email de l'utilisateur courant (extrait du header X-API-Key ou JWT).

    En mode multi-tenant, lève une RuntimeError si l'identité n'a pas été
    posée par le middleware (évite de tomber silencieusement sur USER_EMAIL).
    En mode single-user / DEV_MODE, fallback sur USER_EMAIL.
    """
    email = _current_user_email.get()
    if email:
        return email
    if _MULTI_TENANT and not DEV_MODE:
        raise RuntimeError(
            "Identité utilisateur non définie. "
            "Le middleware d'authentification n'a pas posé l'identité pour cette requête."
        )
    return USER_EMAIL
