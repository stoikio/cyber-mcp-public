"""Admin Panel — FastAPI server (separate process on ADMIN_PORT)."""

import os
from contextlib import asynccontextmanager
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from gateway.config import DATABASE_URL, logger
from gateway.db import init_db, close_db

from admin.backend.auth import router as auth_router, load_admin_emails
from admin.backend.routes.stats import router as stats_router
from admin.backend.routes.policies import router as policies_router
from admin.backend.routes.api_keys import router as api_keys_router
from admin.backend.routes.audit import router as audit_router
from admin.backend.routes.oauth_clients import router as oauth_clients_router
from admin.backend.routes.slack_channels import router as slack_channels_router
from admin.backend.routes.integrations import router as integrations_router
from admin.backend.routes.blocked_emails import router as blocked_emails_router

ADMIN_PORT = int(os.getenv("ADMIN_PORT", "8001"))
ADMIN_HOST = os.getenv("ADMIN_HOST", "127.0.0.1")
ADMIN_CORS_ORIGINS = os.getenv("ADMIN_CORS_ORIGINS", "")


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_admin_emails()
    await init_db()
    logger.info(
        "ADMIN | Démarré sur %s:%d  (DB=%s)",
        ADMIN_HOST,
        ADMIN_PORT,
        DATABASE_URL.split("@")[-1] if "@" in DATABASE_URL else DATABASE_URL,
    )
    yield
    await close_db()


app = FastAPI(
    title="MCP Gateway Admin",
    version="1.0.0",
    lifespan=lifespan,
)

_cors_origins = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    f"http://localhost:{ADMIN_PORT}",
    f"http://127.0.0.1:{ADMIN_PORT}",
]
if ADMIN_CORS_ORIGINS:
    _cors_origins.extend(o.strip() for o in ADMIN_CORS_ORIGINS.split(",") if o.strip())

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(stats_router)
app.include_router(policies_router)
app.include_router(api_keys_router)
app.include_router(audit_router)
app.include_router(oauth_clients_router)
app.include_router(slack_channels_router)
app.include_router(integrations_router)
app.include_router(blocked_emails_router)

_FRONTEND_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"
if _FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=str(_FRONTEND_DIST), html=True), name="spa")


if __name__ == "__main__":
    uvicorn.run(
        "admin.backend.server:app",
        host=ADMIN_HOST,
        port=ADMIN_PORT,
        reload=True,
    )
