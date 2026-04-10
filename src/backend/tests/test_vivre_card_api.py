"""Tests for Vivre Card REST API endpoints."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from app.models.enums import CheckpointReason, CrewRole
from app.models.vivre_card import VivreCard

VOYAGE_ID = uuid.uuid4()
CARD_ID = uuid.uuid4()


def _make_card(
    voyage_id: uuid.UUID | None = None,
    crew_member: str = "captain",
    state_data: dict[str, Any] | None = None,
    reason: str = "interval",
    card_id: uuid.UUID | None = None,
) -> VivreCard:
    card = VivreCard(
        id=card_id or uuid.uuid4(),
        voyage_id=voyage_id or VOYAGE_ID,
        crew_member=crew_member,
        state_data=state_data or {"step": 1},
        checkpoint_reason=reason,
    )
    card.created_at = datetime.now(UTC)
    return card


class TestCreateCheckpoint:
    @pytest.mark.asyncio
    async def test_create_checkpoint_201(self) -> None:
        from app.api.v1.vivre_cards import create_checkpoint
        from app.schemas.vivre_card import VivreCardCreate

        card = _make_card(voyage_id=VOYAGE_ID)
        body = VivreCardCreate(
            crew_member=CrewRole.CAPTAIN,
            state_data={"step": 1},
            checkpoint_reason=CheckpointReason.INTERVAL,
        )
        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID
        mushi = AsyncMock()

        with patch("app.api.v1.vivre_cards.checkpoint", new_callable=AsyncMock) as mock_cp:
            mock_cp.return_value = card
            result = await create_checkpoint(VOYAGE_ID, body, session, voyage, mushi)

        assert result.voyage_id == VOYAGE_ID
        mock_cp.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_create_checkpoint_publishes_event(self) -> None:
        from app.api.v1.vivre_cards import create_checkpoint
        from app.schemas.vivre_card import VivreCardCreate

        card = _make_card(voyage_id=VOYAGE_ID)
        body = VivreCardCreate(
            crew_member=CrewRole.CAPTAIN,
            state_data={"step": 1},
            checkpoint_reason=CheckpointReason.INTERVAL,
        )
        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID
        mushi = AsyncMock()

        with patch("app.api.v1.vivre_cards.checkpoint", new_callable=AsyncMock) as mock_cp:
            mock_cp.return_value = card
            await create_checkpoint(VOYAGE_ID, body, session, voyage, mushi)

        mushi.publish.assert_awaited_once()
        published_event = mushi.publish.call_args[0][1]
        assert published_event.event_type == "checkpoint_created"


class TestListCheckpoints:
    @pytest.mark.asyncio
    async def test_list_checkpoints(self) -> None:
        from app.api.v1.vivre_cards import list_checkpoints

        cards = [_make_card(voyage_id=VOYAGE_ID) for _ in range(2)]

        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        with patch("app.api.v1.vivre_cards.list_cards", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = (cards, 2)
            result = await list_checkpoints(
                VOYAGE_ID, session, voyage, crew_member=None, limit=20, offset=0
            )

        assert result.total == 2
        assert len(result.items) == 2
        assert result.limit == 20
        assert result.offset == 0

    @pytest.mark.asyncio
    async def test_list_checkpoints_filter_crew(self) -> None:
        from app.api.v1.vivre_cards import list_checkpoints

        cards = [_make_card(voyage_id=VOYAGE_ID, crew_member="navigator")]

        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        with patch("app.api.v1.vivre_cards.list_cards", new_callable=AsyncMock) as mock_list:
            mock_list.return_value = (cards, 1)
            await list_checkpoints(
                VOYAGE_ID, session, voyage, crew_member=CrewRole.NAVIGATOR, limit=20, offset=0
            )

        mock_list.assert_awaited_once()
        call_kwargs = mock_list.call_args
        assert call_kwargs[1].get("crew_member") == "navigator"


class TestGetCheckpoint:
    @pytest.mark.asyncio
    async def test_get_checkpoint_by_id(self) -> None:
        from app.api.v1.vivre_cards import get_checkpoint

        card = _make_card(card_id=CARD_ID, voyage_id=VOYAGE_ID)

        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        with patch("app.api.v1.vivre_cards.restore", new_callable=AsyncMock) as mock_restore:
            mock_restore.return_value = card
            result = await get_checkpoint(VOYAGE_ID, CARD_ID, session, voyage)

        assert result.id == CARD_ID

    @pytest.mark.asyncio
    async def test_get_checkpoint_not_found_404(self) -> None:
        from app.api.v1.vivre_cards import get_checkpoint
        from app.services.vivre_card_service import VivreCardError

        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        with patch("app.api.v1.vivre_cards.restore", new_callable=AsyncMock) as mock_restore:
            mock_restore.side_effect = VivreCardError("CARD_NOT_FOUND", "Not found", 404)
            with pytest.raises(HTTPException) as exc_info:
                await get_checkpoint(VOYAGE_ID, uuid.uuid4(), session, voyage)

        assert exc_info.value.status_code == 404


class TestDiffCheckpoints:
    @pytest.mark.asyncio
    async def test_diff_checkpoints(self) -> None:
        from app.api.v1.vivre_cards import diff_checkpoints

        card_a_id = uuid.uuid4()
        card_b_id = uuid.uuid4()
        diff_result = {
            "added": {"output": "done"},
            "removed": {},
            "changed": {"step": {"before": 1, "after": 3}},
        }

        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        with patch("app.api.v1.vivre_cards.diff", new_callable=AsyncMock) as mock_diff:
            mock_diff.return_value = diff_result
            result = await diff_checkpoints(
                VOYAGE_ID, card_a_id, session, voyage, compare_to=card_b_id
            )

        assert result.card_a_id == card_a_id
        assert result.card_b_id == card_b_id
        assert result.added == {"output": "done"}


class TestRestoreCheckpoint:
    @pytest.mark.asyncio
    async def test_restore_checkpoint(self) -> None:
        from app.api.v1.vivre_cards import restore_checkpoint

        card = _make_card(card_id=CARD_ID, voyage_id=VOYAGE_ID, state_data={"step": 5})

        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        with patch("app.api.v1.vivre_cards.restore", new_callable=AsyncMock) as mock_restore:
            mock_restore.return_value = card
            result = await restore_checkpoint(VOYAGE_ID, CARD_ID, session, voyage)

        assert result.card_id == CARD_ID
        assert result.state_data == {"step": 5}
        assert result.restored_at is not None


class TestCleanupCheckpoints:
    @pytest.mark.asyncio
    async def test_cleanup_checkpoints(self) -> None:
        from app.api.v1.vivre_cards import cleanup_checkpoints

        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        with patch("app.api.v1.vivre_cards.cleanup", new_callable=AsyncMock) as mock_cleanup:
            mock_cleanup.return_value = (8, 10)
            result = await cleanup_checkpoints(VOYAGE_ID, session, voyage)

        assert result.deleted_count == 8
        assert result.kept_count == 10
        assert result.voyage_id == VOYAGE_ID


class TestAuthorization:
    @pytest.mark.asyncio
    async def test_get_authorized_voyage_rejects_missing_user(self) -> None:
        """get_current_user dependency raises 401 when no token is provided."""
        from app.api.v1.dependencies import get_current_user

        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(credentials=None, session=AsyncMock())

        assert exc_info.value.status_code == 401

    @pytest.mark.asyncio
    async def test_get_authorized_voyage_rejects_wrong_voyage(self) -> None:
        """get_authorized_voyage raises 404 when voyage doesn't belong to user."""
        from app.api.v1.dependencies import get_authorized_voyage

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None  # no matching voyage
        session.execute.return_value = mock_result

        user = MagicMock()
        user.id = uuid.uuid4()

        with pytest.raises(HTTPException) as exc_info:
            await get_authorized_voyage(uuid.uuid4(), session, user)

        assert exc_info.value.status_code == 404


class TestCrossVoyageScoping:
    @pytest.mark.asyncio
    async def test_get_checkpoint_from_other_voyage_returns_404(self) -> None:
        """Card exists but belongs to a different voyage — must return 404."""
        from app.api.v1.vivre_cards import get_checkpoint
        from app.services.vivre_card_service import VivreCardError

        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        foreign_card_id = uuid.uuid4()
        with patch("app.api.v1.vivre_cards.restore", new_callable=AsyncMock) as mock_restore:
            mock_restore.side_effect = VivreCardError("CARD_NOT_FOUND", "Not found", 404)
            with pytest.raises(HTTPException) as exc_info:
                await get_checkpoint(VOYAGE_ID, foreign_card_id, session, voyage)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_restore_from_other_voyage_returns_404(self) -> None:
        """Restore a card that belongs to another voyage — must return 404."""
        from app.api.v1.vivre_cards import restore_checkpoint
        from app.services.vivre_card_service import VivreCardError

        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        foreign_card_id = uuid.uuid4()
        with patch("app.api.v1.vivre_cards.restore", new_callable=AsyncMock) as mock_restore:
            mock_restore.side_effect = VivreCardError("CARD_NOT_FOUND", "Not found", 404)
            with pytest.raises(HTTPException) as exc_info:
                await restore_checkpoint(VOYAGE_ID, foreign_card_id, session, voyage)

        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_diff_with_foreign_card_returns_404(self) -> None:
        """Diffing against a card from another voyage — must return 404."""
        from app.api.v1.vivre_cards import diff_checkpoints
        from app.services.vivre_card_service import VivreCardError

        session = AsyncMock()
        voyage = MagicMock()
        voyage.id = VOYAGE_ID

        with patch("app.api.v1.vivre_cards.diff", new_callable=AsyncMock) as mock_diff:
            mock_diff.side_effect = VivreCardError("CARD_NOT_FOUND", "Not found", 404)
            with pytest.raises(HTTPException) as exc_info:
                await diff_checkpoints(
                    VOYAGE_ID,
                    uuid.uuid4(),
                    session,
                    voyage,
                    compare_to=uuid.uuid4(),
                )

        assert exc_info.value.status_code == 404
