"""
Configuration centralisée du Secure MCP Gateway.
Charge le fichier .env puis expose toutes les variables comme constantes module-level.
"""

import os
import secrets
import logging
from pathlib import Path

# ─── .env loading ────────────────────────────────────────────────

BASE_DIR = Path(__file__).resolve().parent.parent

_dotenv_path = BASE_DIR / ".env"
if _dotenv_path.exists():
    with open(_dotenv_path) as _f:
        for _line in _f:
            _line = _line.strip()
            if not _line or _line.startswith("#") or "=" not in _line:
                continue
            _k, _, _v = _line.partition("=")
            _k = _k.strip()
            _v = _v.strip().strip('"').strip("'")
            if _k and _k not in os.environ:
                os.environ[_k] = _v

# ─── General ─────────────────────────────────────────────────────

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
DEV_MODE = os.getenv("DEV_MODE", "").lower() in ("1", "true", "yes")

USER_EMAIL = os.getenv("USER_EMAIL", "dev@example.com")
CALENDAR_TIMEZONE = os.getenv("CALENDAR_TIMEZONE", "Europe/Paris")

# ─── Encryption ──────────────────────────────────────────────────

ENCRYPTION_KEY = os.getenv("ENCRYPTION_KEY", "")

# ─── OAuth2 / Google Workspace ───────────────────────────────────

GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
JWT_SECRET = os.getenv("JWT_SECRET", "") or secrets.token_urlsafe(32)
ADMIN_JWT_SECRET = os.getenv("ADMIN_JWT_SECRET", "") or secrets.token_urlsafe(32)
ALLOWED_EMAIL_DOMAIN = os.getenv("ALLOWED_EMAIL_DOMAIN", "")

GATEWAY_DOMAIN = os.getenv("GATEWAY_DOMAIN", "localhost:8000")
OAUTH_ISSUER = os.getenv("OAUTH_ISSUER", f"https://{GATEWAY_DOMAIN}")

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"

# ─── Persistance (Option C) ─────────────────────────────────────

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://mcp:changeme@localhost:5433/mcp_gateway",
)
DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "10"))
DATABASE_POOL_OVERFLOW = int(os.getenv("DATABASE_POOL_OVERFLOW", "5"))
DATABASE_SSL = os.getenv("DATABASE_SSL", "").lower() in ("1", "true", "yes", "require")

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6380/0")

# ─── Network ─────────────────────────────────────────────────────

HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8000"))

# ─── Logging setup ───────────────────────────────────────────────

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("secure-mcp-gateway")
