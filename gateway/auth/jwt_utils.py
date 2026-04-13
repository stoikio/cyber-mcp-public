"""Création et validation de JWT (HS256) pour les sessions OAuth2."""

from datetime import datetime, timezone, timedelta

from gateway.config import JWT_SECRET, OAUTH_ISSUER

_JWT_AUDIENCE = "secure-mcp-gateway"


def create_jwt(email: str) -> str:
    """Crée un JWT signé HS256 contenant l'email de l'utilisateur (durée 1h)."""
    import jwt as pyjwt

    now = datetime.now(timezone.utc)
    payload = {
        "sub": email,
        "iss": OAUTH_ISSUER,
        "aud": _JWT_AUDIENCE,
        "iat": now,
        "exp": now + timedelta(hours=1),
    }
    return pyjwt.encode(payload, JWT_SECRET, algorithm="HS256")


def validate_jwt(token: str) -> str | None:
    """Valide un JWT et retourne l'email (sub) ou None si invalide."""
    import jwt as pyjwt

    try:
        payload = pyjwt.decode(
            token, JWT_SECRET, algorithms=["HS256"],
            issuer=OAUTH_ISSUER, audience=_JWT_AUDIENCE,
        )
        sub = payload.get("sub")
        if not isinstance(sub, str) or not sub:
            return None
        return sub
    except pyjwt.InvalidTokenError:
        return None
