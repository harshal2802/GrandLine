"""Tests for VivreCardService — checkpoint, restore, list, diff, cleanup."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.enums import CheckpointReason, CrewRole
from app.models.vivre_card import VivreCard


def _make_card(
    voyage_id: uuid.UUID | None = None,
    crew_member: str = "captain",
    state_data: dict[str, Any] | None = None,
    reason: str = "interval",
    card_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
) -> VivreCard:
    card = VivreCard(
        id=card_id or uuid.uuid4(),
        voyage_id=voyage_id or uuid.uuid4(),
        crew_member=crew_member,
        state_data=state_data or {"step": 1, "context": "test"},
        checkpoint_reason=reason,
    )
    # Simulate the server_default
    card.created_at = created_at or datetime.now(UTC)
    return card


VOYAGE_ID = uuid.uuid4()


class TestCheckpoint:
    @pytest.mark.asyncio
    async def test_checkpoint_creates_card(self) -> None:
        from app.services.vivre_card_service import checkpoint

        session = AsyncMock()
        state = {"step": 3, "messages": ["hello"]}

        card = await checkpoint(
            session,
            voyage_id=VOYAGE_ID,
            crew_member=CrewRole.CAPTAIN.value,
            state_data=state,
            reason=CheckpointReason.INTERVAL.value,
        )

        session.add.assert_called_once()
        session.commit.assert_awaited_once()
        session.refresh.assert_awaited_once()
        assert card.voyage_id == VOYAGE_ID
        assert card.crew_member == "captain"
        assert card.state_data == state
        assert card.checkpoint_reason == "interval"

    @pytest.mark.asyncio
    async def test_checkpoint_stores_nested_jsonb_state(self) -> None:
        from app.services.vivre_card_service import checkpoint

        session = AsyncMock()
        nested_state = {
            "step": 5,
            "context": {"messages": [{"role": "user", "content": "plan"}]},
            "metadata": {"tokens_used": 150, "model": "claude-sonnet-4-20250514"},
        }

        card = await checkpoint(
            session,
            voyage_id=VOYAGE_ID,
            crew_member=CrewRole.NAVIGATOR.value,
            state_data=nested_state,
            reason=CheckpointReason.MIGRATION.value,
        )

        assert card.state_data == nested_state


class TestRestore:
    @pytest.mark.asyncio
    async def test_restore_returns_card(self) -> None:
        from app.services.vivre_card_service import restore

        card_id = uuid.uuid4()
        expected_card = _make_card(card_id=card_id, voyage_id=VOYAGE_ID)

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = expected_card
        session.execute.return_value = mock_result

        result = await restore(session, card_id)

        assert result.id == card_id
        assert result.state_data == expected_card.state_data

    @pytest.mark.asyncio
    async def test_restore_not_found_raises(self) -> None:
        from app.services.vivre_card_service import VivreCardError, restore

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(VivreCardError) as exc_info:
            await restore(session, uuid.uuid4())

        assert exc_info.value.code == "CARD_NOT_FOUND"
        assert exc_info.value.status_code == 404


class TestListCards:
    @pytest.mark.asyncio
    async def test_list_cards_by_voyage(self) -> None:
        from app.services.vivre_card_service import list_cards

        cards = [_make_card(voyage_id=VOYAGE_ID) for _ in range(3)]

        session = AsyncMock()
        # First call: items query
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = cards
        # Second call: count query
        count_result = MagicMock()
        count_result.scalar_one.return_value = 3
        session.execute.side_effect = [items_result, count_result]

        items, total = await list_cards(session, VOYAGE_ID)

        assert len(items) == 3
        assert total == 3

    @pytest.mark.asyncio
    async def test_list_cards_filter_by_crew_member(self) -> None:
        from app.services.vivre_card_service import list_cards

        cards = [_make_card(voyage_id=VOYAGE_ID, crew_member="captain")]

        session = AsyncMock()
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = cards
        count_result = MagicMock()
        count_result.scalar_one.return_value = 1
        session.execute.side_effect = [items_result, count_result]

        items, total = await list_cards(session, VOYAGE_ID, crew_member="captain")

        assert len(items) == 1
        assert total == 1

    @pytest.mark.asyncio
    async def test_list_cards_pagination(self) -> None:
        from app.services.vivre_card_service import list_cards

        cards = [_make_card(voyage_id=VOYAGE_ID)]

        session = AsyncMock()
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = cards
        count_result = MagicMock()
        count_result.scalar_one.return_value = 10  # total is more than returned
        session.execute.side_effect = [items_result, count_result]

        items, total = await list_cards(session, VOYAGE_ID, limit=5, offset=5)

        assert len(items) == 1
        assert total == 10

    @pytest.mark.asyncio
    async def test_list_cards_empty(self) -> None:
        from app.services.vivre_card_service import list_cards

        session = AsyncMock()
        items_result = MagicMock()
        items_result.scalars.return_value.all.return_value = []
        count_result = MagicMock()
        count_result.scalar_one.return_value = 0
        session.execute.side_effect = [items_result, count_result]

        items, total = await list_cards(session, VOYAGE_ID)

        assert items == []
        assert total == 0


class TestDiff:
    @pytest.mark.asyncio
    async def test_diff_added_keys(self) -> None:
        from app.services.vivre_card_service import diff

        card_a = _make_card(state_data={"step": 1})
        card_b = _make_card(state_data={"step": 1, "output": "done"})

        session = AsyncMock()
        mock_result_a = MagicMock()
        mock_result_a.scalar_one_or_none.return_value = card_a
        mock_result_b = MagicMock()
        mock_result_b.scalar_one_or_none.return_value = card_b
        session.execute.side_effect = [mock_result_a, mock_result_b]

        result = await diff(session, card_a.id, card_b.id)

        assert result["added"] == {"output": "done"}
        assert result["removed"] == {}
        assert result["changed"] == {}

    @pytest.mark.asyncio
    async def test_diff_removed_keys(self) -> None:
        from app.services.vivre_card_service import diff

        card_a = _make_card(state_data={"step": 1, "temp": "val"})
        card_b = _make_card(state_data={"step": 1})

        session = AsyncMock()
        mock_result_a = MagicMock()
        mock_result_a.scalar_one_or_none.return_value = card_a
        mock_result_b = MagicMock()
        mock_result_b.scalar_one_or_none.return_value = card_b
        session.execute.side_effect = [mock_result_a, mock_result_b]

        result = await diff(session, card_a.id, card_b.id)

        assert result["added"] == {}
        assert result["removed"] == {"temp": "val"}
        assert result["changed"] == {}

    @pytest.mark.asyncio
    async def test_diff_changed_keys(self) -> None:
        from app.services.vivre_card_service import diff

        card_a = _make_card(state_data={"step": 1, "status": "running"})
        card_b = _make_card(state_data={"step": 3, "status": "done"})

        session = AsyncMock()
        mock_result_a = MagicMock()
        mock_result_a.scalar_one_or_none.return_value = card_a
        mock_result_b = MagicMock()
        mock_result_b.scalar_one_or_none.return_value = card_b
        session.execute.side_effect = [mock_result_a, mock_result_b]

        result = await diff(session, card_a.id, card_b.id)

        assert result["changed"]["step"] == {"before": 1, "after": 3}
        assert result["changed"]["status"] == {"before": "running", "after": "done"}

    @pytest.mark.asyncio
    async def test_diff_identical_states(self) -> None:
        from app.services.vivre_card_service import diff

        state = {"step": 1, "context": "same"}
        card_a = _make_card(state_data=state)
        card_b = _make_card(state_data=state.copy())

        session = AsyncMock()
        mock_result_a = MagicMock()
        mock_result_a.scalar_one_or_none.return_value = card_a
        mock_result_b = MagicMock()
        mock_result_b.scalar_one_or_none.return_value = card_b
        session.execute.side_effect = [mock_result_a, mock_result_b]

        result = await diff(session, card_a.id, card_b.id)

        assert result["added"] == {}
        assert result["removed"] == {}
        assert result["changed"] == {}

    @pytest.mark.asyncio
    async def test_diff_card_not_found_raises(self) -> None:
        from app.services.vivre_card_service import VivreCardError, diff

        session = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        session.execute.return_value = mock_result

        with pytest.raises(VivreCardError) as exc_info:
            await diff(session, uuid.uuid4(), uuid.uuid4())

        assert exc_info.value.code == "CARD_NOT_FOUND"


class TestCleanup:
    @pytest.mark.asyncio
    async def test_cleanup_deletes_old_cards(self) -> None:
        from app.services.vivre_card_service import cleanup

        session = AsyncMock()
        # First query: distinct crew members
        crew_result = MagicMock()
        crew_result.scalars.return_value.all.return_value = ["captain"]
        # Second query: all card IDs for captain ordered by created_at desc
        ids = [uuid.uuid4() for _ in range(5)]
        card_ids_result = MagicMock()
        card_ids_result.scalars.return_value.all.return_value = ids
        # Third query: delete returns count
        delete_result = MagicMock()
        delete_result.rowcount = 3

        session.execute.side_effect = [crew_result, card_ids_result, delete_result]

        deleted, kept = await cleanup(session, VOYAGE_ID, keep_last_n=2)

        assert deleted == 3
        assert kept == 2
        session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_cleanup_no_cards(self) -> None:
        from app.services.vivre_card_service import cleanup

        session = AsyncMock()
        crew_result = MagicMock()
        crew_result.scalars.return_value.all.return_value = []
        session.execute.return_value = crew_result

        deleted, kept = await cleanup(session, VOYAGE_ID, keep_last_n=5)

        assert deleted == 0
        assert kept == 0

    @pytest.mark.asyncio
    async def test_cleanup_keeps_all_when_under_limit(self) -> None:
        from app.services.vivre_card_service import cleanup

        session = AsyncMock()
        crew_result = MagicMock()
        crew_result.scalars.return_value.all.return_value = ["navigator"]
        # Only 2 cards, keep_last_n=5 — nothing to delete
        ids = [uuid.uuid4() for _ in range(2)]
        card_ids_result = MagicMock()
        card_ids_result.scalars.return_value.all.return_value = ids
        session.execute.side_effect = [crew_result, card_ids_result]

        deleted, kept = await cleanup(session, VOYAGE_ID, keep_last_n=5)

        assert deleted == 0
        assert kept == 2
