"""API key management endpoints."""

import hashlib
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from gateway.db import ApiKey, async_session

from admin.backend.auth import get_admin_user
from admin.backend.schemas import ApiKeyCreate, ApiKeyCreated, ApiKeyOut

router = APIRouter(prefix="/api/api-keys", tags=["api-keys"])


@router.get("", response_model=list[ApiKeyOut])
async def list_api_keys(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        rows = (
            await session.execute(
                select(ApiKey)
                .order_by(ApiKey.created_at.desc())
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()

    return [
        ApiKeyOut(
            hash_prefix=r.key_hash[:8],
            email=r.email,
            created_at=r.created_at,
            expires_at=r.expires_at,
            revoked=r.revoked,
        )
        for r in rows
    ]


@router.post("", response_model=ApiKeyCreated, status_code=status.HTTP_201_CREATED)
async def create_api_key(
    body: ApiKeyCreate,
    _admin: str = Depends(get_admin_user),
):
    raw_key = str(uuid.uuid4())
    key_hash = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    expires_at = datetime.now(timezone.utc) + timedelta(days=body.expires_in_days)

    async with async_session() as session:
        row = ApiKey(
            key_hash=key_hash,
            email=body.email,
            expires_at=expires_at,
        )
        session.add(row)
        await session.commit()

    return ApiKeyCreated(
        api_key=raw_key,
        hash_prefix=key_hash[:8],
        email=body.email,
        expires_at=expires_at,
    )


@router.post("/{hash_prefix}/revoke", status_code=status.HTTP_200_OK)
async def revoke_api_key(
    hash_prefix: str,
    _admin: str = Depends(get_admin_user),
):
    if len(hash_prefix) < 8:
        raise HTTPException(
            status_code=400,
            detail="Le préfixe de hash doit contenir au moins 8 caractères.",
        )

    async with async_session() as session:
        rows = (
            await session.execute(
                select(ApiKey).where(
                    ApiKey.key_hash.startswith(hash_prefix),
                    ApiKey.revoked.is_(False),
                )
            )
        ).scalars().all()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail="Aucune clé active trouvée avec ce préfixe",
            )

        if len(rows) > 1:
            raise HTTPException(
                status_code=409,
                detail=f"Préfixe ambigu : {len(rows)} clés correspondent. Utilisez un préfixe plus long.",
            )

        for row in rows:
            row.revoked = True
            session.add(row)
        await session.commit()

    return {"revoked": len(rows), "hash_prefix": hash_prefix}
