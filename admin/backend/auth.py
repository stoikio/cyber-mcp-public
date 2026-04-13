"""Admin authentication: API-key login and JWT-protected dependency."""

import hashlib
import os
from datetime import datetime, timedelta, timezone

import jwt as pyjwt
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select

from gateway.config import ADMIN_JWT_SECRET, OAUTH_ISSUER
from gateway.db import ApiKey, async_session

from admin.backend.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/api/auth", tags=["auth"])

_bearer = HTTPBearer(auto_error=False)

ADMIN_EMAILS: set[str] = set()


def load_admin_emails() -> None:
    raw = os.getenv("ADMIN_EMAILS", "")
    ADMIN_EMAILS.clear()
    ADMIN_EMAILS.update(
        e.strip().lower() for e in raw.split(",") if e.strip()
    )


def _create_admin_jwt(email: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "iss": OAUTH_ISSUER,
        "iat": now,
        "exp": now + timedelta(hours=2),
        "role": "admin",
    }
    return pyjwt.encode(payload, ADMIN_JWT_SECRET, algorithm="HS256")


def _validate_admin_jwt(token: str) -> str | None:
    try:
        payload = pyjwt.decode(
            token, ADMIN_JWT_SECRET, algorithms=["HS256"], issuer=OAUTH_ISSUER
        )
        if payload.get("role") != "admin":
            return None
        return payload.get("sub")
    except pyjwt.InvalidTokenError:
        return None


async def get_admin_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str:
    """FastAPI dependency that enforces admin JWT on every protected route."""
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentification requise",
        )
    email = _validate_admin_jwt(credentials.credentials)
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token invalide ou expiré",
        )
    return email


@router.post("/login", response_model=LoginResponse)
async def login(body: LoginRequest):
    key_hash = hashlib.sha256(body.api_key.encode("utf-8")).hexdigest()

    async with async_session() as session:
        row = await session.get(ApiKey, key_hash)

    if row is None or row.revoked:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Clé API invalide ou révoquée",
        )

    if row.expires_at:
        exp = row.expires_at
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Clé API expirée",
            )

    email = row.email.lower()
    if email not in ADMIN_EMAILS:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Accès réservé aux administrateurs",
        )

    token = _create_admin_jwt(email)
    return LoginResponse(token=token, email=email, expires_in=7200)
