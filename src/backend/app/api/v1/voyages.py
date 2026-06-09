"""Voyage lifecycle endpoints.

``POST /voyages`` — chart a course. Creates the voyage (status CHARTED) plus a
default dial config so the pipeline and dial endpoints work immediately; the
mapping can be customized afterwards via ``PUT /voyages/{id}/dial-config``.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_current_user
from app.core.config import settings
from app.models import get_db
from app.models.dial_config import DialConfig
from app.models.enums import CrewRole, VoyageStatus
from app.models.user import User
from app.models.voyage import Voyage
from app.schemas.voyage import VoyageCreate, VoyageRead

router = APIRouter(prefix="/voyages", tags=["voyages"])


def _default_dial_config(voyage_id: uuid.UUID) -> DialConfig:
    """Every crew role dials the deployment's default provider/model."""
    return DialConfig(
        id=uuid.uuid4(),
        voyage_id=voyage_id,
        role_mapping={
            role.value: {
                "provider": settings.dial_default_provider,
                "model": settings.dial_default_model,
            }
            for role in CrewRole
        },
        fallback_chain=None,
    )


@router.post("", response_model=VoyageRead, status_code=status.HTTP_201_CREATED)
async def create_voyage(
    body: VoyageCreate,
    session: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Voyage:
    voyage = Voyage(
        id=uuid.uuid4(),
        user_id=user.id,
        title=body.title,
        description=body.description,
        target_repo=body.target_repo,
        status=VoyageStatus.CHARTED.value,
        phase_status={},
    )
    session.add(voyage)
    await session.flush()

    session.add(_default_dial_config(voyage.id))

    await session.commit()
    await session.refresh(voyage)
    return voyage
