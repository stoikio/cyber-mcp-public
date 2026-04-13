"""CRUD endpoints for Slack channel configuration."""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select

from gateway.db import SlackChannel, async_session

from admin.backend.auth import get_admin_user
from admin.backend.schemas import SlackChannelCreate, SlackChannelOut, SlackChannelUpdate

router = APIRouter(prefix="/api/slack-channels", tags=["slack-channels"])


@router.get("", response_model=list[SlackChannelOut])
async def list_slack_channels(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        rows = (
            await session.execute(
                select(SlackChannel)
                .order_by(SlackChannel.channel_name)
                .offset(offset)
                .limit(limit)
            )
        ).scalars().all()
    return [SlackChannelOut.model_validate(r) for r in rows]


@router.post("", response_model=SlackChannelOut, status_code=status.HTTP_201_CREATED)
async def create_slack_channel(
    body: SlackChannelCreate,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        existing = (
            await session.execute(
                select(SlackChannel).where(SlackChannel.channel_id == body.channel_id)
            )
        ).scalar_one_or_none()
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Le canal « {body.channel_id} » est déjà configuré",
            )
        row = SlackChannel(**body.model_dump())
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return SlackChannelOut.model_validate(row)


@router.get("/{channel_pk}", response_model=SlackChannelOut)
async def get_slack_channel(
    channel_pk: int,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(SlackChannel, channel_pk)
    if row is None:
        raise HTTPException(status_code=404, detail="Canal introuvable")
    return SlackChannelOut.model_validate(row)


@router.put("/{channel_pk}", response_model=SlackChannelOut)
async def update_slack_channel(
    channel_pk: int,
    body: SlackChannelUpdate,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(SlackChannel, channel_pk)
        if row is None:
            raise HTTPException(status_code=404, detail="Canal introuvable")
        updates = body.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(row, key, value)
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return SlackChannelOut.model_validate(row)


@router.delete("/{channel_pk}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_slack_channel(
    channel_pk: int,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(SlackChannel, channel_pk)
        if row is None:
            raise HTTPException(status_code=404, detail="Canal introuvable")
        await session.delete(row)
        await session.commit()


@router.patch("/{channel_pk}/toggle", response_model=SlackChannelOut)
async def toggle_slack_channel(
    channel_pk: int,
    _admin: str = Depends(get_admin_user),
):
    async with async_session() as session:
        row = await session.get(SlackChannel, channel_pk)
        if row is None:
            raise HTTPException(status_code=404, detail="Canal introuvable")
        row.enabled = not row.enabled
        session.add(row)
        await session.commit()
        await session.refresh(row)
    return SlackChannelOut.model_validate(row)
