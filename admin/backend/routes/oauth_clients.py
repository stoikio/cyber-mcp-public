"""Read-only endpoint for OAuth clients."""

from fastapi import APIRouter, Depends
from sqlalchemy import select

from gateway.db import OAuthClient, async_session

from admin.backend.auth import get_admin_user
from admin.backend.schemas import OAuthClientOut

router = APIRouter(prefix="/api/oauth-clients", tags=["oauth-clients"])


@router.get("", response_model=list[OAuthClientOut])
async def list_oauth_clients(
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        rows = (
            await session.execute(
                select(OAuthClient).order_by(OAuthClient.created_at.desc())
            )
        ).scalars().all()
    return [OAuthClientOut.model_validate(r) for r in rows]
