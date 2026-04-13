"""CRUD endpoints for security policies."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from gateway.db import Policy, async_session

from admin.backend.auth import get_admin_user
from admin.backend.schemas import PolicyCreate, PolicyOut, PolicyUpdate

router = APIRouter(prefix="/api/policies", tags=["policies"])


@router.get("", response_model=list[PolicyOut])
async def list_policies(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        rows = (
            await session.execute(
                select(Policy)
                .order_by(Policy.priority.desc(), Policy.id)
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
    return [PolicyOut.model_validate(r) for r in rows]


@router.post("", response_model=PolicyOut, status_code=status.HTTP_201_CREATED)
async def create_policy(
    body: PolicyCreate,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        existing = (
            await session.execute(
                select(Policy).where(Policy.name == body.name)
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Une politique nommée « {body.name} » existe déjà",
            )
        row = Policy(**body.model_dump())
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return PolicyOut.model_validate(row)


@router.get("/{policy_id}", response_model=PolicyOut)
async def get_policy(
    policy_id: int,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(Policy, policy_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Politique introuvable")
    return PolicyOut.model_validate(row)


@router.put("/{policy_id}", response_model=PolicyOut)
async def update_policy(
    policy_id: int,
    body: PolicyUpdate,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(Policy, policy_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Politique introuvable")
        updates = body.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(row, key, value)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return PolicyOut.model_validate(row)


@router.delete("/{policy_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_policy(
    policy_id: int,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(Policy, policy_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Politique introuvable")
        await session.delete(row)
        await session.commit()


@router.patch("/{policy_id}/toggle", response_model=PolicyOut)
async def toggle_policy(
    policy_id: int,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(Policy, policy_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Politique introuvable")
        row.enabled = not row.enabled
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return PolicyOut.model_validate(row)
