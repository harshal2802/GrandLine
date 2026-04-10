"""REST API endpoints for Vivre Card state checkpointing."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.dependencies import get_authorized_voyage, get_den_den_mushi
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import CheckpointCreatedEvent
from app.den_den_mushi.mushi import DenDenMushi
from app.models import get_db
from app.models.enums import CrewRole
from app.models.voyage import Voyage
from app.schemas.vivre_card import (
    CleanupResult,
    VivreCardCreate,
    VivreCardDiff,
    VivreCardList,
    VivreCardRead,
    VivreCardRestore,
)
from app.services.vivre_card_service import (
    VivreCardError,
    checkpoint,
    cleanup,
    diff,
    list_cards,
    restore,
)

router = APIRouter(prefix="/voyages/{voyage_id}/vivre-cards", tags=["vivre-cards"])


@router.post("", response_model=VivreCardRead, status_code=201)
async def create_checkpoint(
    voyage_id: uuid.UUID,
    body: VivreCardCreate,
    session: AsyncSession = Depends(get_db),
    voyage: Voyage = Depends(get_authorized_voyage),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
) -> VivreCardRead:
    try:
        card = await checkpoint(
            session,
            voyage_id=voyage_id,
            crew_member=body.crew_member.value,
            state_data=body.state_data,
            reason=body.checkpoint_reason.value,
        )
    except VivreCardError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc

    event = CheckpointCreatedEvent(
        voyage_id=voyage_id,
        source_role=body.crew_member,
        payload={
            "card_id": str(card.id),
            "crew_member": body.crew_member.value,
            "reason": body.checkpoint_reason.value,
        },
    )
    await mushi.publish(stream_key(voyage_id), event)

    return VivreCardRead.model_validate(card)


@router.get("", response_model=VivreCardList)
async def list_checkpoints(
    voyage_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    voyage: Voyage = Depends(get_authorized_voyage),
    crew_member: CrewRole | None = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> VivreCardList:
    member_str = crew_member.value if crew_member else None
    items, total = await list_cards(
        session, voyage_id, crew_member=member_str, limit=limit, offset=offset
    )
    return VivreCardList(
        items=[VivreCardRead.model_validate(c) for c in items],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{card_id}", response_model=VivreCardRead)
async def get_checkpoint(
    voyage_id: uuid.UUID,
    card_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    voyage: Voyage = Depends(get_authorized_voyage),
) -> VivreCardRead:
    try:
        card = await restore(session, card_id, voyage_id)
    except VivreCardError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    return VivreCardRead.model_validate(card)


@router.get("/{card_id}/diff", response_model=VivreCardDiff)
async def diff_checkpoints(
    voyage_id: uuid.UUID,
    card_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    voyage: Voyage = Depends(get_authorized_voyage),
    compare_to: uuid.UUID = Query(...),
) -> VivreCardDiff:
    try:
        result = await diff(session, card_id, compare_to, voyage_id)
    except VivreCardError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    return VivreCardDiff(
        card_a_id=card_id,
        card_b_id=compare_to,
        **result,
    )


@router.post("/{card_id}/restore", response_model=VivreCardRestore)
async def restore_checkpoint(
    voyage_id: uuid.UUID,
    card_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    voyage: Voyage = Depends(get_authorized_voyage),
) -> VivreCardRestore:
    try:
        card = await restore(session, card_id, voyage_id)
    except VivreCardError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail={"error": {"code": exc.code, "message": exc.message}},
        ) from exc
    return VivreCardRestore(
        card_id=card.id,
        voyage_id=card.voyage_id,
        crew_member=card.crew_member,
        state_data=card.state_data,
        checkpoint_reason=card.checkpoint_reason,
        restored_at=datetime.now(UTC),
    )


@router.delete("/cleanup", response_model=CleanupResult)
async def cleanup_checkpoints(
    voyage_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    voyage: Voyage = Depends(get_authorized_voyage),
    keep_last_n: int = Query(default=10, ge=1),
) -> CleanupResult:
    deleted, kept = await cleanup(session, voyage_id, keep_last_n=keep_last_n)
    return CleanupResult(
        deleted_count=deleted,
        kept_count=kept,
        voyage_id=voyage_id,
    )
