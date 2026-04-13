"""
Audit structuré — PostgreSQL (requêtable) + fichier optionnel (transitoire).
Le fichier audit.log est activé uniquement si le répertoire est accessible en écriture
(désactivé automatiquement sur les systèmes de fichiers en lecture seule).
"""

import json
import logging
import os
from datetime import datetime, timezone

from gateway.config import BASE_DIR, logger
from gateway.db import AuditEvent, async_session

# ─── File-based audit (optionnel, désactivé si FS non-writable) ──

AUDIT_LOG_FILE = BASE_DIR / "audit.log"
DISABLE_AUDIT_FILE = os.getenv("DISABLE_AUDIT_FILE", "").lower() in ("1", "true", "yes")

_audit_file_logger: logging.Logger | None = None

if not DISABLE_AUDIT_FILE:
    try:
        _handler = logging.FileHandler(AUDIT_LOG_FILE, encoding="utf-8")
        _handler.setFormatter(logging.Formatter("%(message)s"))
        _audit_file_logger = logging.getLogger("mcp-audit")
        _audit_file_logger.setLevel(logging.INFO)
        _audit_file_logger.propagate = False
        _audit_file_logger.addHandler(_handler)
    except OSError:
        logger.info("AUDIT | audit.log non accessible en écriture — audit fichier désactivé")
        _audit_file_logger = None
else:
    logger.info("AUDIT | Audit fichier désactivé (DISABLE_AUDIT_FILE=true)")


# ─── Public API ──────────────────────────────────────────────────

_current_user_func = None


def set_current_user_func(func):
    """Injecte la fonction get_current_user depuis le module auth."""
    global _current_user_func
    _current_user_func = func


def _get_user() -> str:
    if _current_user_func:
        try:
            return _current_user_func()
        except RuntimeError:
            return ""
    return ""


_SENSITIVE_FIELDS = frozenset({
    "body", "text", "description", "params",
    "api_key", "token", "access_token", "refresh_token", "password",
})

_MAX_DETAIL_VALUE_LEN = 500


def _sanitize_audit_details(kwargs: dict) -> dict:
    """Retire ou tronque les champs sensibles avant stockage en audit."""
    details = {}
    for k, v in kwargs.items():
        if k in ("event", "user", "tool", "ip"):
            continue
        if k in _SENSITIVE_FIELDS:
            if k == "params" and isinstance(v, dict):
                details[k] = {
                    pk: (f"[{len(pv)} chars]" if isinstance(pv, str) and len(pv) > _MAX_DETAIL_VALUE_LEN else pv)
                    for pk, pv in v.items()
                    if pk not in _SENSITIVE_FIELDS
                }
            elif isinstance(v, str) and len(v) > _MAX_DETAIL_VALUE_LEN:
                details[k] = f"[{len(v)} chars — tronqué]"
            else:
                continue
        else:
            if isinstance(v, str) and len(v) > _MAX_DETAIL_VALUE_LEN:
                details[k] = v[:_MAX_DETAIL_VALUE_LEN] + "…"
            else:
                details[k] = v
    return details


async def audit(event: str, user: str = "", tool: str = "", ip: str = "", **kwargs):
    """Enregistre un événement d'audit en DB + fichier."""
    user = user or _get_user()

    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        "user": user,
        "tool": tool,
    }
    safe_details = _sanitize_audit_details(kwargs)
    entry.update(safe_details)

    # 1) Fichier (synchrone, optionnel)
    if _audit_file_logger:
        _audit_file_logger.info(json.dumps(entry, ensure_ascii=False))

    # 2) PostgreSQL (async)
    try:
        async with async_session() as session:
            row = AuditEvent(
                event=event,
                user_email=user,
                tool=tool,
                ip=ip,
                details=safe_details,
            )
            session.add(row)
            await session.commit()
    except Exception as e:
        logger.warning("AUDIT | Échec écriture PG (fichier OK) : %s", e)
