"""
Endpoints OAuth2 — RFC 8414 metadata, RFC 7591 Dynamic Client Registration,
Authorization Code + PKCE, token exchange.
Clients persistés en PG. Sessions et codes éphémères en Redis.
"""

import base64
import hashlib
import hmac
import html as html_mod
import json
import secrets
import urllib.parse

from starlette.requests import Request as StarletteRequest
from starlette.responses import Response as StarletteResponse, HTMLResponse, RedirectResponse

from gateway.config import (
    GOOGLE_CLIENT_ID,
    GOOGLE_CLIENT_SECRET,
    GOOGLE_AUTH_URL,
    GOOGLE_TOKEN_URL,
    GOOGLE_USERINFO_URL,
    OAUTH_ISSUER,
    ALLOWED_EMAIL_DOMAIN,
    logger,
)
from gateway.db import OAuthClient, async_session
from gateway.auth.jwt_utils import create_jwt
from gateway.security.audit import audit
from gateway.redis_client import ttl_set, ttl_pop


# ─── PKCE ────────────────────────────────────────────────────────


def _verify_pkce(code_verifier: str, code_challenge: str) -> bool:
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    computed = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return hmac.compare_digest(computed, code_challenge)


# ─── OAuth Metadata ──────────────────────────────────────────────


async def oauth_metadata(request: StarletteRequest) -> StarletteResponse:
    """GET /.well-known/oauth-authorization-server — RFC 8414."""
    return StarletteResponse(
        content=json.dumps({
            "issuer": OAUTH_ISSUER,
            "authorization_endpoint": f"{OAUTH_ISSUER}/oauth/authorize",
            "token_endpoint": f"{OAUTH_ISSUER}/oauth/token",
            "registration_endpoint": f"{OAUTH_ISSUER}/oauth/register",
            "response_types_supported": ["code"],
            "grant_types_supported": ["authorization_code"],
            "code_challenge_methods_supported": ["S256"],
            "token_endpoint_auth_methods_supported": ["none"],
        }),
        media_type="application/json",
    )


async def oauth_protected_resource(request: StarletteRequest) -> StarletteResponse:
    """GET /.well-known/oauth-protected-resource — RFC 9728."""
    return StarletteResponse(
        content=json.dumps({
            "resource": f"{OAUTH_ISSUER}/mcp",
            "authorization_servers": [OAUTH_ISSUER],
            "bearer_methods_supported": ["header"],
        }),
        media_type="application/json",
    )


# ─── Dynamic Client Registration ────────────────────────────────


_ALLOWED_REDIRECT_SCHEMES = ("http", "https")
_MAX_REDIRECT_URIS = 5
_DCR_RATE_KEY = "rate:dcr:global"
_DCR_RATE_LIMIT = 20
_DCR_RATE_WINDOW = 3600


async def oauth_register(request: StarletteRequest) -> StarletteResponse:
    """POST /oauth/register — RFC 7591 with rate limiting and redirect_uri validation."""
    from gateway.redis_client import rate_limit_check

    allowed, count = await rate_limit_check(_DCR_RATE_KEY, _DCR_RATE_LIMIT, _DCR_RATE_WINDOW)
    if not allowed:
        return StarletteResponse(
            content=json.dumps({"error": "too_many_requests",
                                "error_description": "Trop d'enregistrements de clients. Réessayez plus tard."}),
            status_code=429, media_type="application/json",
        )

    try:
        body = await request.json()
    except Exception:
        return StarletteResponse(
            content=json.dumps({"error": "invalid_client_metadata"}),
            status_code=400, media_type="application/json",
        )

    redirect_uris = body.get("redirect_uris", [])
    if not isinstance(redirect_uris, list) or len(redirect_uris) > _MAX_REDIRECT_URIS:
        return StarletteResponse(
            content=json.dumps({"error": "invalid_client_metadata",
                                "error_description": f"redirect_uris doit être une liste de {_MAX_REDIRECT_URIS} URIs max."}),
            status_code=400, media_type="application/json",
        )
    for uri in redirect_uris:
        if not isinstance(uri, str):
            return StarletteResponse(
                content=json.dumps({"error": "invalid_client_metadata",
                                    "error_description": "Chaque redirect_uri doit être une chaîne."}),
                status_code=400, media_type="application/json",
            )
        parsed = urllib.parse.urlparse(uri)
        if parsed.scheme not in _ALLOWED_REDIRECT_SCHEMES:
            return StarletteResponse(
                content=json.dumps({"error": "invalid_client_metadata",
                                    "error_description": f"Schéma non autorisé dans redirect_uri: {parsed.scheme}"}),
                status_code=400, media_type="application/json",
            )
        if not parsed.hostname:
            return StarletteResponse(
                content=json.dumps({"error": "invalid_client_metadata",
                                    "error_description": "redirect_uri invalide (hostname manquant)."}),
                status_code=400, media_type="application/json",
            )

    client_id = secrets.token_urlsafe(24)
    client_data = {
        "client_id": client_id,
        "client_name": body.get("client_name", "MCP Client")[:200],
        "redirect_uris": redirect_uris,
        "grant_types": body.get("grant_types", ["authorization_code"]),
        "response_types": body.get("response_types", ["code"]),
        "token_endpoint_auth_method": body.get("token_endpoint_auth_method", "none"),
    }

    try:
        async with async_session() as session:
            row = OAuthClient(
                client_id=client_id,
                client_name=client_data["client_name"],
                redirect_uris=client_data["redirect_uris"],
                grant_types=client_data["grant_types"],
                response_types=client_data["response_types"],
                auth_method=client_data.get("token_endpoint_auth_method", "none"),
            )
            session.add(row)
            await session.commit()
    except Exception as e:
        logger.error("OAUTH | Échec enregistrement client en PG")
        return StarletteResponse(
            content=json.dumps({"error": "server_error", "error_description": "Registration failed"}),
            status_code=500, media_type="application/json",
        )

    logger.info("OAUTH | Client enregistré : %s (%s)", client_id[:12], client_data["client_name"])
    return StarletteResponse(
        content=json.dumps(client_data),
        status_code=201, media_type="application/json",
    )


# ─── Authorization ───────────────────────────────────────────────


async def oauth_authorize(request: StarletteRequest) -> StarletteResponse:
    """GET /oauth/authorize — Démarre le flux OAuth2 via Google."""
    if not GOOGLE_CLIENT_ID:
        return StarletteResponse(
            content=json.dumps({"error": "OAuth non configuré (GOOGLE_CLIENT_ID manquant)."}),
            status_code=500, media_type="application/json",
        )

    client_id = request.query_params.get("client_id", "")
    redirect_uri = request.query_params.get("redirect_uri", "")
    response_type = request.query_params.get("response_type", "")
    state = request.query_params.get("state", "")
    code_challenge = request.query_params.get("code_challenge", "")
    code_challenge_method = request.query_params.get("code_challenge_method", "")

    if not client_id:
        return StarletteResponse(
            content=json.dumps({"error": "client_id requis"}),
            status_code=400, media_type="application/json",
        )

    if response_type != "code":
        return StarletteResponse(
            content=json.dumps({"error": "response_type must be 'code'"}),
            status_code=400, media_type="application/json",
        )

    if not code_challenge or code_challenge_method != "S256":
        return StarletteResponse(
            content=json.dumps({"error": "PKCE obligatoire : code_challenge (S256) requis"}),
            status_code=400, media_type="application/json",
        )

    async with async_session() as session:
        client = await session.get(OAuthClient, client_id)
    if not client:
        return StarletteResponse(
            content=json.dumps({"error": "client_id inconnu"}),
            status_code=400, media_type="application/json",
        )

    registered_uris = client.redirect_uris or []
    if not redirect_uri or redirect_uri not in registered_uris:
        return StarletteResponse(
            content=json.dumps({"error": "redirect_uri non enregistré pour ce client"}),
            status_code=400, media_type="application/json",
        )

    gateway_state = secrets.token_urlsafe(32)
    await ttl_set("oauth:session", gateway_state, {
        "client_id": client_id,
        "code_challenge": code_challenge,
        "redirect_uri": redirect_uri,
        "client_state": state,
    }, ttl_seconds=600)

    google_scopes = " ".join([
        "openid", "email", "profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.compose",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ])
    google_params = urllib.parse.urlencode({
        "client_id": GOOGLE_CLIENT_ID,
        "redirect_uri": f"{OAUTH_ISSUER}/oauth/callback",
        "response_type": "code",
        "scope": google_scopes,
        "state": gateway_state,
        "hd": ALLOWED_EMAIL_DOMAIN,
        "access_type": "offline",
        "prompt": "consent",
    })
    google_url = f"{GOOGLE_AUTH_URL}?{google_params}"

    # Serve an HTML page instead of a 302 redirect. This forces the browser
    # to actually visit the gateway domain first. Without this, some MCP
    # clients (e.g. Claude Desktop) follow the 302 programmatically and open
    # only the Google URL in the browser — which can break reverse proxy /
    # tunnel setups that require a prior browser visit.
    safe_url = html_mod.escape(google_url, quote=True)
    page = (
        "<!DOCTYPE html>"
        '<html lang="fr"><head><meta charset="utf-8">'
        f'<meta http-equiv="refresh" content="0;url={safe_url}">'
        "<title>MCP Gateway — Redirection</title>"
        "<style>"
        "body{font-family:system-ui,sans-serif;display:flex;align-items:center;"
        "justify-content:center;min-height:100vh;margin:0;background:#0f172a;color:#e2e8f0}"
        "a{color:#60a5fa}"
        "</style></head><body>"
        '<p>Redirection vers Google… '
        f'<a href="{safe_url}">Cliquez ici</a> si la page ne change pas.</p>'
        f"<script>window.location.replace({json.dumps(google_url)});</script>"
        "</body></html>"
    )
    return HTMLResponse(content=page)


# ─── Callback ────────────────────────────────────────────────────


async def oauth_callback(request: StarletteRequest) -> StarletteResponse:
    """GET /oauth/callback — Reçoit le code Google, émet un code gateway."""
    try:
        return await _oauth_callback_inner(request)
    except Exception as e:
        logger.exception("OAUTH | Erreur non gérée dans /oauth/callback : %s", e)
        return StarletteResponse(
            content=json.dumps({
                "error": "server_error",
                "error_description": f"Erreur interne dans le callback OAuth : {type(e).__name__}: {e}",
            }, ensure_ascii=False),
            status_code=500, media_type="application/json",
        )


async def _oauth_callback_inner(request: StarletteRequest) -> StarletteResponse:
    """Logique interne du callback OAuth."""
    error = request.query_params.get("error", "")
    if error:
        return StarletteResponse(
            content=json.dumps({"error": f"Google OAuth error: {error}"}),
            status_code=400, media_type="application/json",
        )

    google_code = request.query_params.get("code", "")
    gateway_state = request.query_params.get("state", "")

    session_data = await ttl_pop("oauth:session", gateway_state)
    if not session_data:
        return StarletteResponse(
            content=json.dumps({"error": "Session OAuth expirée ou invalide. Recommencez."}),
            status_code=400, media_type="application/json",
        )

    import httpx
    async with httpx.AsyncClient() as client:
        token_resp = await client.post(GOOGLE_TOKEN_URL, data={
            "code": google_code,
            "client_id": GOOGLE_CLIENT_ID,
            "client_secret": GOOGLE_CLIENT_SECRET,
            "redirect_uri": f"{OAUTH_ISSUER}/oauth/callback",
            "grant_type": "authorization_code",
        }, timeout=15)

    if token_resp.status_code != 200:
        logger.error("OAUTH | Google token exchange failed: status=%d", token_resp.status_code)
        return StarletteResponse(
            content=json.dumps({"error": "Échec de l'échange de token avec Google."}),
            status_code=502, media_type="application/json",
        )

    google_tokens = token_resp.json()
    google_access_token = google_tokens.get("access_token", "")

    async with httpx.AsyncClient() as client:
        userinfo_resp = await client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {google_access_token}"},
            timeout=10,
        )

    if userinfo_resp.status_code != 200:
        logger.error("OAUTH | Google userinfo failed: status=%d", userinfo_resp.status_code)
        return StarletteResponse(
            content=json.dumps({"error": "Impossible de récupérer le profil Google."}),
            status_code=502, media_type="application/json",
        )

    userinfo = userinfo_resp.json()
    email = userinfo.get("email", "")
    email_verified = userinfo.get("email_verified", False)

    if not email_verified:
        await audit("AUTH_DOMAIN_REJECTED", tool="oauth", user=email, reason="email_not_verified")
        return StarletteResponse(
            content=json.dumps({"error": "L'adresse email n'est pas vérifiée par Google."}),
            status_code=403, media_type="application/json",
        )

    if ALLOWED_EMAIL_DOMAIN and not email.endswith(f"@{ALLOWED_EMAIL_DOMAIN}"):
        await audit("AUTH_DOMAIN_REJECTED", tool="oauth", user=email, domain=ALLOWED_EMAIL_DOMAIN)
        return StarletteResponse(
            content=json.dumps({"error": f"Seuls les comptes @{ALLOWED_EMAIL_DOMAIN} sont autorisés."}),
            status_code=403, media_type="application/json",
        )

    from gateway.auth import is_email_blocked
    if await is_email_blocked(email):
        await audit("AUTH_BLOCKED_ACCOUNT", tool="oauth", user=email)
        logger.warning("OAUTH | Compte bloqué : %s", email)
        return StarletteResponse(
            content=json.dumps({"error": "Ce compte n'est pas autorisé à accéder au gateway MCP."},
                               ensure_ascii=False),
            status_code=403, media_type="application/json",
        )

    from gateway.backends.token_store import user_token_store
    await user_token_store.save(email, google_tokens)

    auth_code = secrets.token_urlsafe(32)
    await ttl_set("oauth:code", auth_code, {
        "email": email,
        "client_id": session_data.get("client_id", ""),
        "code_challenge": session_data.get("code_challenge", ""),
        "redirect_uri": session_data.get("redirect_uri", ""),
    }, ttl_seconds=300)

    await audit("OAUTH_AUTHORIZED", tool="oauth", user=email)
    logger.info("OAUTH | Utilisateur autorisé : %s (tokens Gmail+Calendar stockés)", email)

    redirect_params = {"code": auth_code}
    if session_data.get("client_state"):
        redirect_params["state"] = session_data["client_state"]

    return RedirectResponse(
        session_data["redirect_uri"] + "?" + urllib.parse.urlencode(redirect_params)
    )


# ─── Token Exchange ──────────────────────────────────────────────


async def oauth_token(request: StarletteRequest) -> StarletteResponse:
    """POST /oauth/token — Échange le code gateway contre un JWT."""
    content_type = request.headers.get("content-type", "")
    if "application/x-www-form-urlencoded" in content_type:
        form = await request.form()
        params = dict(form)
    elif "application/json" in content_type:
        params = await request.json()
    else:
        params = dict(request.query_params)

    grant_type = params.get("grant_type", "")
    code = params.get("code", "")
    code_verifier = params.get("code_verifier", "")
    client_id = params.get("client_id", "")
    redirect_uri = params.get("redirect_uri", "")

    if grant_type != "authorization_code":
        return StarletteResponse(
            content=json.dumps({"error": "unsupported_grant_type"}),
            status_code=400, media_type="application/json",
        )

    code_data = await ttl_pop("oauth:code", code)
    if not code_data:
        return StarletteResponse(
            content=json.dumps({"error": "invalid_grant", "error_description": "Code invalide ou expiré."}),
            status_code=400, media_type="application/json",
        )

    if client_id and code_data.get("client_id") and client_id != code_data["client_id"]:
        return StarletteResponse(
            content=json.dumps({"error": "invalid_grant", "error_description": "client_id mismatch."}),
            status_code=400, media_type="application/json",
        )
    if redirect_uri and code_data.get("redirect_uri") and redirect_uri != code_data["redirect_uri"]:
        return StarletteResponse(
            content=json.dumps({"error": "invalid_grant", "error_description": "redirect_uri mismatch."}),
            status_code=400, media_type="application/json",
        )

    stored_challenge = code_data.get("code_challenge", "")
    if not stored_challenge:
        return StarletteResponse(
            content=json.dumps({"error": "invalid_grant", "error_description": "Code émis sans PKCE — rejet."}),
            status_code=400, media_type="application/json",
        )
    if not code_verifier or not _verify_pkce(code_verifier, stored_challenge):
        return StarletteResponse(
            content=json.dumps({"error": "invalid_grant", "error_description": "PKCE verification failed."}),
            status_code=400, media_type="application/json",
        )

    email = code_data["email"]
    access_token = create_jwt(email)

    await audit("OAUTH_TOKEN_ISSUED", tool="oauth", user=email)

    return StarletteResponse(
        content=json.dumps({
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": 3600,
        }),
        media_type="application/json",
    )
