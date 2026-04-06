from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.models import get_db
from app.models.dial_config import DialConfig
from app.models.user import User
from app.schemas.dial_config import DialConfigRead, DialConfigUpdate

router = APIRouter(prefix="/voyages", tags=["dial-system"])


@router.get("/{voyage_id}/dial-config", response_model=DialConfigRead)
async def get_dial_config(
    voyage_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DialConfig:
    result = await session.execute(select(DialConfig).where(DialConfig.voyage_id == voyage_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Dial config not found for this voyage")
    return config


@router.put("/{voyage_id}/dial-config", response_model=DialConfigRead)
async def update_dial_config(
    voyage_id: uuid.UUID,
    body: DialConfigUpdate,
    session: AsyncSession = Depends(get_db),
    _user: User = Depends(get_current_user),
) -> DialConfig:
    result = await session.execute(select(DialConfig).where(DialConfig.voyage_id == voyage_id))
    config = result.scalar_one_or_none()
    if config is None:
        raise HTTPException(status_code=404, detail="Dial config not found for this voyage")

    if body.role_mapping is not None:
        config.role_mapping = body.role_mapping
    if body.fallback_chain is not None:
        config.fallback_chain = body.fallback_chain

    await session.commit()
    await session.refresh(config)
    return config
