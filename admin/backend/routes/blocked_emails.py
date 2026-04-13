"""CRUD endpoints for blocked email patterns."""

import re

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from gateway.db import BlockedEmailPattern, async_session

from admin.backend.auth import get_admin_user
from admin.backend.schemas import (
    BlockedEmailPatternCreate,
    BlockedEmailPatternOut,
    BlockedEmailPatternUpdate,
)

router = APIRouter(prefix="/api/blocked-emails", tags=["blocked-emails"])


def _validate_regex(pattern: str) -> None:
    try:
        re.compile(pattern)
    except re.error as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Expression régulière invalide : {exc}",
        )


@router.get("", response_model=list[BlockedEmailPatternOut])
async def list_patterns(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        rows = (
            await session.execute(
                select(BlockedEmailPattern)
                .order_by(BlockedEmailPattern.id)
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
    return [BlockedEmailPatternOut.model_validate(r) for r in rows]


@router.post("", response_model=BlockedEmailPatternOut, status_code=status.HTTP_201_CREATED)
async def create_pattern(
    body: BlockedEmailPatternCreate,
    _admin: str = Depends(get_admin_user),
):
    _validate_regex(body.pattern)
    async with async_session() as session:
        existing = (
            await session.execute(
                select(BlockedEmailPattern).where(BlockedEmailPattern.pattern == body.pattern)
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Le pattern « {body.pattern} » existe déjà",
            )
        row = BlockedEmailPattern(**body.model_dump())
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return BlockedEmailPatternOut.model_validate(row)


@router.get("/{pattern_id}", response_model=BlockedEmailPatternOut)
async def get_pattern(
    pattern_id: int,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(BlockedEmailPattern, pattern_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Pattern introuvable")
    return BlockedEmailPatternOut.model_validate(row)


@router.put("/{pattern_id}", response_model=BlockedEmailPatternOut)
async def update_pattern(
    pattern_id: int,
    body: BlockedEmailPatternUpdate,
    _admin: str = Depends(get_admin_user),
):
    updates = body.model_dump(exclude_unset=True)
    if "pattern" in updates:
        _validate_regex(updates["pattern"])

    async with async_session() as session:
        row = await session.get(BlockedEmailPattern, pattern_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Pattern introuvable")
        for key, value in updates.items():
            setattr(row, key, value)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return BlockedEmailPatternOut.model_validate(row)


@router.delete("/{pattern_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_pattern(
    pattern_id: int,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(BlockedEmailPattern, pattern_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Pattern introuvable")
        await session.delete(row)
        await session.commit()


@router.patch("/{pattern_id}/toggle", response_model=BlockedEmailPatternOut)
async def toggle_pattern(
    pattern_id: int,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(BlockedEmailPattern, pattern_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Pattern introuvable")
        row.enabled = not row.enabled
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return BlockedEmailPatternOut.model_validate(row)
