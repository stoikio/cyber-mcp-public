"""Endpoints for managing integration tokens (Slack, Notion, etc.)."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select

from gateway.db import IntegrationToken, async_session
from gateway.crypto import decrypt_data
from gateway.backends.integration_store import set_token, delete_token, mask_token

from admin.backend.auth import get_admin_user
from admin.backend.schemas import IntegrationStatusOut, IntegrationTokenUpdate

SERVICES = {
    "slack": {
        "name": "Slack",
        "description": "Bot token Slack (xoxb-...) pour envoyer et lire des messages",
    },
    "notion": {
        "name": "Notion",
        "description": "Token d'intégration Notion (ntn_...) pour la lecture de pages et bases de données",
    },
}

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationStatusOut])
async def list_integrations(
    admin_email: str = Depends(get_admin_user),
):
    async with async_session() as session:
        rows = (
            await session.execute(select(IntegrationToken))
        ).scalars().all()

    token_map = {r.service: r for r in rows}
    result = []

    for svc_key, svc_info in SERVICES.items():
        row = token_map.get(svc_key)
        if row:
            plain = decrypt_data(row.encrypted_value)
            result.append(IntegrationStatusOut(
                service=svc_key,
                name=svc_info["name"],
                description=svc_info["description"],
                configured=True,
                mode="configured",
                masked_value=mask_token(plain),
                label=row.label,
                updated_by=row.updated_by,
                updated_at=row.updated_at,
            ))
        else:
            result.append(IntegrationStatusOut(
                service=svc_key,
                name=svc_info["name"],
                description=svc_info["description"],
                configured=False,
                mode="non configuré",
                masked_value="",
                label="",
                updated_by="",
                updated_at=None,
            ))

    return result


@router.put("/{service}", response_model=IntegrationStatusOut)
async def update_integration(
    service: str,
    body: IntegrationTokenUpdate,
    admin_email: str = Depends(get_admin_user),
):
    if service not in SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service inconnu : {service}. Services disponibles : {', '.join(SERVICES)}",
        )

    await set_token(service, body.value, label=body.label, updated_by=admin_email)

    return IntegrationStatusOut(
        service=service,
        name=SERVICES[service]["name"],
        description=SERVICES[service]["description"],
        configured=True,
        mode="configured",
        masked_value=mask_token(body.value),
        label=body.label,
        updated_by=admin_email,
    )


@router.delete("/{service}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_integration(
    service: str,
    admin_email: str = Depends(get_admin_user),
):
    if service not in SERVICES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Service inconnu : {service}",
        )
    found = await delete_token(service)
    if not found:
        raise HTTPException(status_code=404, detail=f"Aucun token configuré pour {service}")


@router.post("/{service}/test")
async def test_integration(
    service: str,
    admin_email: str = Depends(get_admin_user),
):
    """Teste la connexion d'une intégration."""
    from gateway.backends.integration_store import get_token as _get_token

    token = await _get_token(service)
    if not token:
        return {"service": service, "status": "error", "message": "Aucun token configuré"}

    if service == "slack":
        try:
            from slack_sdk import WebClient
            client = WebClient(token=token)
            auth = client.auth_test()
            return {
                "service": "slack",
                "status": "ok",
                "bot_name": auth.get("user", "?"),
                "team": auth.get("team", "?"),
            }
        except Exception as e:
            return {"service": "slack", "status": "error", "message": str(e)}

    elif service == "notion":
        try:
            import httpx
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    "https://api.notion.com/v1/users/me",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "Notion-Version": "2022-06-28",
                    },
                    timeout=10,
                )
                resp.raise_for_status()
                data = resp.json()
            return {
                "service": "notion",
                "status": "ok",
                "bot_name": data.get("name", "?"),
                "type": data.get("type", "?"),
            }
        except Exception as e:
            return {"service": "notion", "status": "error", "message": str(e)}

    return {"service": service, "status": "error", "message": "Test non implémenté"}
