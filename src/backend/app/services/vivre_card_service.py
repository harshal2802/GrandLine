"""VivreCardService — agent state checkpoint, restore, list, diff, and cleanup."""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete, distinct, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.vivre_card import VivreCard


class VivreCardError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code


async def checkpoint(
    session: AsyncSession,
    voyage_id: uuid.UUID,
    crew_member: str,
    state_data: dict[str, Any],
    reason: str,
) -> VivreCard:
    """Create a new Vivre Card checkpoint."""
    card = VivreCard(
        voyage_id=voyage_id,
        crew_member=crew_member,
        state_data=state_data,
        checkpoint_reason=reason,
    )
    session.add(card)
    await session.commit()
    await session.refresh(card)
    return card


async def restore(session: AsyncSession, card_id: uuid.UUID, voyage_id: uuid.UUID) -> VivreCard:
    """Fetch a Vivre Card by ID, scoped to a voyage. Raises VivreCardError if not found."""
    result = await session.execute(
        select(VivreCard).where(VivreCard.id == card_id, VivreCard.voyage_id == voyage_id)
    )
    card = result.scalar_one_or_none()
    if card is None:
        raise VivreCardError("CARD_NOT_FOUND", "Vivre Card not found", 404)
    return card


async def list_cards(
    session: AsyncSession,
    voyage_id: uuid.UUID,
    crew_member: str | None = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[VivreCard], int]:
    """List Vivre Cards for a voyage with optional crew member filter and pagination."""
    query = select(VivreCard).where(VivreCard.voyage_id == voyage_id)
    count_query = select(func.count(VivreCard.id)).where(VivreCard.voyage_id == voyage_id)

    if crew_member is not None:
        query = query.where(VivreCard.crew_member == crew_member)
        count_query = count_query.where(VivreCard.crew_member == crew_member)

    query = query.order_by(VivreCard.created_at.desc()).limit(limit).offset(offset)

    items_result = await session.execute(query)
    items = list(items_result.scalars().all())

    count_result = await session.execute(count_query)
    total = count_result.scalar_one()

    return items, total


async def diff(
    session: AsyncSession,
    card_id_a: uuid.UUID,
    card_id_b: uuid.UUID,
    voyage_id: uuid.UUID,
) -> dict[str, Any]:
    """Compute a shallow diff between two Vivre Card state snapshots, scoped to a voyage."""
    result_a = await session.execute(
        select(VivreCard).where(VivreCard.id == card_id_a, VivreCard.voyage_id == voyage_id)
    )
    card_a = result_a.scalar_one_or_none()
    if card_a is None:
        raise VivreCardError("CARD_NOT_FOUND", f"Vivre Card {card_id_a} not found", 404)

    result_b = await session.execute(
        select(VivreCard).where(VivreCard.id == card_id_b, VivreCard.voyage_id == voyage_id)
    )
    card_b = result_b.scalar_one_or_none()
    if card_b is None:
        raise VivreCardError("CARD_NOT_FOUND", f"Vivre Card {card_id_b} not found", 404)

    state_a = card_a.state_data
    state_b = card_b.state_data

    keys_a = set(state_a.keys())
    keys_b = set(state_b.keys())

    added = {k: state_b[k] for k in keys_b - keys_a}
    removed = {k: state_a[k] for k in keys_a - keys_b}
    changed = {
        k: {"before": state_a[k], "after": state_b[k]}
        for k in keys_a & keys_b
        if state_a[k] != state_b[k]
    }

    return {"added": added, "removed": removed, "changed": changed}


async def cleanup(
    session: AsyncSession,
    voyage_id: uuid.UUID,
    keep_last_n: int = 10,
) -> tuple[int, int]:
    """Delete old checkpoints per crew member, keeping the N most recent."""
    # Get distinct crew members for this voyage
    crew_result = await session.execute(
        select(distinct(VivreCard.crew_member)).where(VivreCard.voyage_id == voyage_id)
    )
    crew_members = list(crew_result.scalars().all())

    if not crew_members:
        return 0, 0

    total_deleted = 0
    total_kept = 0

    for member in crew_members:
        # Get all card IDs for this member ordered by created_at desc
        ids_result = await session.execute(
            select(VivreCard.id)
            .where(VivreCard.voyage_id == voyage_id, VivreCard.crew_member == member)
            .order_by(VivreCard.created_at.desc())
        )
        all_ids = list(ids_result.scalars().all())

        ids_to_keep = all_ids[:keep_last_n]
        ids_to_delete = all_ids[keep_last_n:]

        total_kept += len(ids_to_keep)

        if ids_to_delete:
            result = await session.execute(delete(VivreCard).where(VivreCard.id.in_(ids_to_delete)))
            total_deleted += result.rowcount

    if total_deleted > 0:
        await session.commit()

    return total_deleted, total_kept
