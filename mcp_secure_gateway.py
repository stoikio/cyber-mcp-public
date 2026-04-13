"""
Secure MCP Gateway (Redis + PostgreSQL)
=======================================
Entrypoint : initialise l'infrastructure (DB, Redis), instancie les backends,
enregistre les tools MCP, monte les routes OAuth2, et lance le serveur.

Usage :
  docker compose up -d          # Lance PG + Redis
  python3 mcp_secure_gateway.py # Lance le gateway

Config Claude Desktop :
  { "mcpServers": { "secure-mcp-gateway": { "url": "http://localhost:8000/mcp" } } }
"""

import os
from contextlib import asynccontextmanager

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from sqlalchemy import text
from starlette.requests import Request as StarletteRequest
from starlette.responses import JSONResponse
from starlette.routing import Route

from gateway.config import (
    HOST,
    PORT,
    LOG_LEVEL,
    DEV_MODE,
    GATEWAY_DOMAIN,
    GOOGLE_CLIENT_ID,
    OAUTH_ISSUER,
    ALLOWED_EMAIL_DOMAIN,
    logger,
)
from gateway.crypto import fernet
from gateway.db import init_db, close_db, async_session as async_session_factory
from gateway.redis_client import init_redis, close_redis
from gateway.security.audit import set_current_user_func
from gateway.security.policies import load_policies
from gateway.auth import get_current_user
from gateway.auth.middleware import UserIdentMiddleware
from gateway.auth.oauth import (
    oauth_metadata,
    oauth_protected_resource,
    oauth_register,
    oauth_authorize,
    oauth_callback,
    oauth_token,
)
from gateway.backends.gmail import GmailBackend
from gateway.backends.slack import SlackBackend
from gateway.backends.calendar_gw import CalendarBackend
from gateway.backends.notion import NotionBackend
from gateway.backends.token_store import user_token_store
from gateway.tools import register_all_tools

# ─── Audit needs access to get_current_user ──────────────────────

set_current_user_func(get_current_user)

# ─── Instantiate backends ────────────────────────────────────────

gmail = GmailBackend()
slack = SlackBackend()
calendar = CalendarBackend()
notion = NotionBackend()

# ─── FastMCP Server ──────────────────────────────────────────────

mcp = FastMCP(
    "secure-mcp-gateway",
    stateless_http=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=True,
        allowed_hosts=[
            "127.0.0.1:*", "127.0.0.1",
            "localhost:*", "localhost",
            "[::1]:*", "[::1]",
            f"{GATEWAY_DOMAIN}:*", GATEWAY_DOMAIN,
        ],
        allowed_origins=[
            "https://" + GATEWAY_DOMAIN,
            "http://127.0.0.1:*", "http://localhost:*",
        ],
    ),
)

# ─── Register MCP Tools ──────────────────────────────────────────

register_all_tools(mcp, gmail=gmail, slack=slack, calendar=calendar, notion=notion)

# ─── Main ────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn

    @asynccontextmanager
    async def lifespan(app):
        # ── Startup ──
        await init_redis()
        await init_db()
        await load_policies()
        await slack.reload_from_db()
        await notion.reload_from_db()
        token_count = await user_token_store.count()

        if DEV_MODE and GOOGLE_CLIENT_ID:
            logger.critical(
                "SÉCURITÉ : DEV_MODE activé alors que GOOGLE_CLIENT_ID est configuré. "
                "Cela contourne toute l'authentification. Désactivez DEV_MODE en production."
            )
            raise SystemExit(1)

        logger.info("=== Secure MCP Gateway ===")
        logger.info("Security: DEV_MODE=%s | Encryption=%s",
                     "ON" if DEV_MODE else "OFF",
                     "ON" if fernet else "OFF")
        if not fernet:
            logger.warning(
                "ENCRYPTION_KEY non configuré — les tokens ne pourront pas être stockés. "
                "Générez une clé : python3 migrate_security.py --generate-encryption-key"
            )
        logger.info("OAuth2: Google=%s | Issuer=%s | Domain=%s",
                     "ON" if GOOGLE_CLIENT_ID else "OFF",
                     OAUTH_ISSUER, ALLOWED_EMAIL_DOMAIN)
        if not os.getenv("JWT_SECRET"):
            logger.warning("JWT_SECRET non défini — secret auto-généré (perdu au redémarrage). "
                           "Ajoutez JWT_SECRET dans .env pour la persistance des sessions.")
        logger.info("Persistence: PostgreSQL=ON | Redis=ON")
        logger.info("User tokens: %d in DB | Gmail: %s | Slack: %s | Calendar: %s | Notion: %s",
                     token_count, gmail.mode, slack.mode, calendar.mode, notion.mode)

        yield

        # ── Shutdown ──
        await close_redis()
        await close_db()

    app = mcp.streamable_http_app()

    # Wrap the MCP lifespan (which initializes the session manager task group)
    # with our own startup/shutdown for DB, Redis, etc.
    mcp_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def combined_lifespan(app_arg):
        async with mcp_lifespan(app_arg):
            async with lifespan(app_arg):
                yield

    app.router.lifespan_context = combined_lifespan

    async def health_check(request: StarletteRequest):
        checks = {"postgresql": "ok", "redis": "ok"}
        status_code = 200

        try:
            async with async_session_factory() as session:
                await session.execute(text("SELECT 1"))
        except Exception as e:
            checks["postgresql"] = f"error: {type(e).__name__}"
            status_code = 503

        try:
            from gateway.redis_client import get_redis
            r = get_redis()
            await r.ping()
        except Exception as e:
            checks["redis"] = f"error: {type(e).__name__}"
            status_code = 503

        return JSONResponse({"status": "ok" if status_code == 200 else "degraded", **checks}, status_code=status_code)

    oauth_routes = [
        Route("/health", health_check, methods=["GET"]),
        Route("/.well-known/oauth-authorization-server", oauth_metadata, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource/{path:path}", oauth_protected_resource, methods=["GET"]),
        Route("/.well-known/oauth-protected-resource", oauth_protected_resource, methods=["GET"]),
        Route("/oauth/register", oauth_register, methods=["POST"]),
        Route("/oauth/authorize", oauth_authorize, methods=["GET"]),
        Route("/oauth/callback", oauth_callback, methods=["GET"]),
        Route("/oauth/token", oauth_token, methods=["POST"]),
    ]
    for route in oauth_routes:
        app.routes.insert(0, route)

    app.add_middleware(UserIdentMiddleware)

    uvicorn.run(app, host=HOST, port=PORT, log_level=LOG_LEVEL.lower())
