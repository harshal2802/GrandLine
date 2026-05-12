"""Tests for CrewAction helper (Phase 16.0).

Covers P3 (event_id correlation), P8 (locked enum), P13 (canonical timestamp).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.den_den_mushi.events import CrewActionRecordedEvent
from app.models.crew_action import CrewAction
from app.models.enums import CrewRole
from app.services.crew_action_helper import (
    CrewActionType,
    publish_crew_action_recorded,
    record_action,
)

VOYAGE_ID = uuid.uuid4()


def _mock_session() -> MagicMock:
    sess = MagicMock()
    sess.add = MagicMock()
    return sess


class TestRecordAction:
    def test_appends_row_no_commit_no_flush(self) -> None:
        sess = _mock_session()

        action = record_action(
            sess,
            VOYAGE_ID,
            CrewRole.CAPTAIN,
            CrewActionType.PLAN_CREATED,
            "Captain charted course with 3 phases",
            {"plan_id": str(uuid.uuid4()), "phase_count": 3},
        )

        assert isinstance(action, CrewAction)
        assert action.voyage_id == VOYAGE_ID
        assert action.crew_member == "captain"
        assert action.action_type == "plan_created"
        sess.add.assert_called_once_with(action)

    def test_generates_event_id_into_details(self) -> None:
        sess = _mock_session()

        action = record_action(
            sess,
            VOYAGE_ID,
            CrewRole.CAPTAIN,
            CrewActionType.PLAN_CREATED,
            "summary",
            {"foo": "bar"},
        )

        assert "event_id" in action.details
        # round-trip parses as UUID
        uuid.UUID(action.details["event_id"])
        # caller-supplied keys preserved
        assert action.details["foo"] == "bar"

    def test_no_caller_details_still_generates_event_id(self) -> None:
        sess = _mock_session()

        action = record_action(sess, VOYAGE_ID, CrewRole.CAPTAIN, CrewActionType.PLAN_CREATED, "s")

        assert "event_id" in action.details
        uuid.UUID(action.details["event_id"])

    def test_rejects_caller_supplied_event_id(self) -> None:
        sess = _mock_session()

        with pytest.raises(ValueError, match="event_id"):
            record_action(
                sess,
                VOYAGE_ID,
                CrewRole.CAPTAIN,
                CrewActionType.PLAN_CREATED,
                "s",
                {"event_id": "stolen"},
            )

    def test_rejects_summary_over_200_chars(self) -> None:
        sess = _mock_session()

        with pytest.raises(ValueError, match="200"):
            record_action(
                sess,
                VOYAGE_ID,
                CrewRole.CAPTAIN,
                CrewActionType.PLAN_CREATED,
                "x" * 201,
            )

    def test_summary_at_200_chars_ok(self) -> None:
        sess = _mock_session()

        action = record_action(
            sess,
            VOYAGE_ID,
            CrewRole.CAPTAIN,
            CrewActionType.PLAN_CREATED,
            "x" * 200,
        )
        assert action.summary == "x" * 200

    def test_rejects_ad_hoc_action_type_string(self) -> None:
        sess = _mock_session()

        with pytest.raises(TypeError, match="CrewActionType"):
            record_action(
                sess,
                VOYAGE_ID,
                CrewRole.CAPTAIN,
                "plan_created",  # type: ignore[arg-type]
                "s",
            )

    def test_does_not_commit_or_flush(self) -> None:
        sess = MagicMock()
        sess.commit = AsyncMock()
        sess.flush = AsyncMock()
        sess.add = MagicMock()

        record_action(sess, VOYAGE_ID, CrewRole.CAPTAIN, CrewActionType.PLAN_CREATED, "s")

        sess.commit.assert_not_awaited()
        sess.flush.assert_not_awaited()


class TestPublishCrewActionRecorded:
    @pytest.mark.asyncio
    async def test_publishes_event_with_canonical_payload(self) -> None:
        mushi = AsyncMock()
        mushi.publish = AsyncMock(return_value="msg-1")

        action = CrewAction(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            crew_member="captain",
            action_type="plan_created",
            summary="ok",
            details={"event_id": str(uuid.uuid4()), "plan_id": str(uuid.uuid4())},
        )
        action.created_at = datetime(2026, 4, 30, tzinfo=UTC)

        await publish_crew_action_recorded(mushi, VOYAGE_ID, action)

        mushi.publish.assert_awaited_once()
        event = mushi.publish.await_args.args[1]
        assert isinstance(event, CrewActionRecordedEvent)
        assert event.event_type == "crew_action_recorded"
        assert event.voyage_id == VOYAGE_ID
        assert event.source_role == CrewRole.CAPTAIN
        # P3 correlation: event payload event_id matches the row's details event_id
        assert event.payload["event_id"] == action.details["event_id"]
        assert event.payload["crew_action_id"] == str(action.id)
        assert event.payload["action_type"] == "plan_created"
        assert event.payload["summary"] == "ok"
        # P13 canonical timestamp present in payload
        assert event.payload["created_at"] == "2026-04-30T00:00:00+00:00"

    @pytest.mark.asyncio
    async def test_swallows_publish_failure(self) -> None:
        mushi = AsyncMock()
        mushi.publish = AsyncMock(side_effect=ConnectionError("redis down"))

        action = CrewAction(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            crew_member="captain",
            action_type="plan_created",
            summary="ok",
            details={"event_id": str(uuid.uuid4())},
        )
        action.created_at = datetime(2026, 4, 30, tzinfo=UTC)

        # Should not raise — durable record is the DB row.
        await publish_crew_action_recorded(mushi, VOYAGE_ID, action)

    @pytest.mark.asyncio
    async def test_unknown_crew_member_falls_back_to_captain(self) -> None:
        mushi = AsyncMock()
        mushi.publish = AsyncMock(return_value="msg-1")

        action = CrewAction(
            id=uuid.uuid4(),
            voyage_id=VOYAGE_ID,
            crew_member="unknown_role",  # not a CrewRole value
            action_type="plan_created",
            summary="ok",
            details={"event_id": str(uuid.uuid4())},
        )
        action.created_at = datetime(2026, 4, 30, tzinfo=UTC)

        await publish_crew_action_recorded(mushi, VOYAGE_ID, action)

        event = mushi.publish.await_args.args[1]
        assert event.source_role == CrewRole.CAPTAIN
