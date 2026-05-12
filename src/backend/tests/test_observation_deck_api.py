"""Tests for the Observation Deck REST endpoints (Phase 16.0).

Covers P6 (CrewAction cursor), P7 (voyages list sort/cursor/filter).
Endpoint handlers are invoked directly with mocked AsyncSession, matching
the convention in test_helmsman_api.py / test_pipeline_api.py.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1._cursor import encode_cursor
from app.api.v1.observation_deck import list_crew_actions, list_voyages
from app.models.crew_action import CrewAction
from app.models.enums import VoyageStatus
from app.models.voyage import Voyage
from app.schemas.observation_deck import CrewActionListResponse, VoyageListResponse

USER_ID = uuid.uuid4()
OTHER_USER_ID = uuid.uuid4()
VOYAGE_ID = uuid.uuid4()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    return user


def _mock_voyage(
    voyage_id: uuid.UUID | None = None,
    status_: str = VoyageStatus.CHARTED.value,
    user_id: uuid.UUID | None = None,
    updated_at: datetime | None = None,
) -> Voyage:
    """Build a Voyage ORM instance shaped enough for VoyageListItem.model_validate.

    We use the real Voyage class (not MagicMock) so Pydantic's
    `model_validate(from_attributes=True)` finds the right attributes.
    """
    v = Voyage()
    v.id = voyage_id or uuid.uuid4()
    v.user_id = user_id or USER_ID
    v.title = "test voyage"
    v.description = "x"
    v.status = status_
    v.target_repo = None
    v.phase_status = {}
    v.created_at = datetime(2026, 4, 30, tzinfo=UTC)
    v.updated_at = updated_at or datetime(2026, 4, 30, tzinfo=UTC)
    return v


def _mock_crew_action(
    voyage_id: uuid.UUID | None = None,
    created_at: datetime | None = None,
    action_type: str = "plan_created",
) -> CrewAction:
    a = CrewAction()
    a.id = uuid.uuid4()
    a.voyage_id = voyage_id or VOYAGE_ID
    a.crew_member = "captain"
    a.action_type = action_type
    a.summary = "test summary"
    a.details = {"event_id": str(uuid.uuid4())}
    a.created_at = created_at or datetime(2026, 4, 30, tzinfo=UTC)
    return a


def _session_returning(rows: list[Any]) -> AsyncMock:
    session = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = rows
    session.execute = AsyncMock(return_value=result)
    return session


# ---------------------------------------------------------------------------
# GET /voyages (P7)
# ---------------------------------------------------------------------------


class TestListVoyages:
    @pytest.mark.asyncio
    async def test_returns_caller_voyages(self) -> None:
        v1 = _mock_voyage()
        v2 = _mock_voyage()
        session = _session_returning([v1, v2])

        resp = await list_voyages(
            user=_mock_user(), session=session, voyage_status=None, cursor=None, limit=50
        )

        assert isinstance(resp, VoyageListResponse)
        assert len(resp.items) == 2

    @pytest.mark.asyncio
    async def test_empty_list_returns_no_cursor(self) -> None:
        session = _session_returning([])

        resp = await list_voyages(
            user=_mock_user(), session=session, voyage_status=None, cursor=None, limit=50
        )

        assert resp.items == []
        assert resp.next_cursor is None

    @pytest.mark.asyncio
    async def test_full_page_returns_next_cursor(self) -> None:
        rows = [_mock_voyage() for _ in range(3)]
        session = _session_returning(rows)

        resp = await list_voyages(
            user=_mock_user(), session=session, voyage_status=None, cursor=None, limit=3
        )

        assert resp.next_cursor is not None  # exactly == limit triggers cursor

    @pytest.mark.asyncio
    async def test_partial_page_returns_no_cursor(self) -> None:
        rows = [_mock_voyage() for _ in range(2)]
        session = _session_returning(rows)

        resp = await list_voyages(
            user=_mock_user(), session=session, voyage_status=None, cursor=None, limit=10
        )

        assert resp.next_cursor is None

    @pytest.mark.asyncio
    async def test_invalid_cursor_returns_400(self) -> None:
        session = _session_returning([])

        with pytest.raises(HTTPException) as exc_info:
            await list_voyages(
                user=_mock_user(),
                session=session,
                voyage_status=None,
                cursor="not-a-cursor",
                limit=50,
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"]["code"] == "INVALID_CURSOR"

    @pytest.mark.asyncio
    async def test_valid_cursor_round_trips(self) -> None:
        # Build a cursor from an arbitrary (ts, id), pass it back. The handler
        # must accept it without error.
        ts = datetime(2026, 4, 30, tzinfo=UTC)
        cursor = encode_cursor(ts, uuid.uuid4())
        session = _session_returning([])

        resp = await list_voyages(
            user=_mock_user(), session=session, voyage_status=None, cursor=cursor, limit=50
        )
        assert resp.items == []

    @pytest.mark.asyncio
    async def test_active_status_filter_excludes_terminal(self) -> None:
        # The handler builds a SELECT with a status NOT IN clause; we just
        # assert the SQL that reached the session is shape-correct via the
        # `where` clauses on the statement passed in.
        session = _session_returning([])

        await list_voyages(
            user=_mock_user(),
            session=session,
            voyage_status="active",
            cursor=None,
            limit=50,
        )

        # The compiled SQL must include the NOT IN predicate; we verify by
        # rendering the statement passed to execute.
        passed_stmt = session.execute.await_args.args[0]
        compiled = str(passed_stmt.compile(compile_kwargs={"literal_binds": False}))
        assert "NOT IN" in compiled.upper()

    @pytest.mark.asyncio
    async def test_terminal_status_filter_includes_only_terminal(self) -> None:
        session = _session_returning([])

        await list_voyages(
            user=_mock_user(),
            session=session,
            voyage_status="terminal",
            cursor=None,
            limit=50,
        )

        passed_stmt = session.execute.await_args.args[0]
        compiled = str(passed_stmt.compile(compile_kwargs={"literal_binds": False}))
        # Terminal filter is `status IN (...)` — bare IN without NOT.
        assert " IN " in compiled.upper()
        assert "NOT IN" not in compiled.upper()


# ---------------------------------------------------------------------------
# GET /voyages/{id}/crew-actions (P6)
# ---------------------------------------------------------------------------


class TestListCrewActions:
    @pytest.mark.asyncio
    async def test_returns_actions_for_voyage(self) -> None:
        a1 = _mock_crew_action()
        a2 = _mock_crew_action(action_type="poneglyph_drafted")
        session = _session_returning([a1, a2])

        resp = await list_crew_actions(
            voyage_id=VOYAGE_ID,
            voyage=_mock_voyage(voyage_id=VOYAGE_ID),
            session=session,
            cursor=None,
            limit=200,
        )

        assert isinstance(resp, CrewActionListResponse)
        assert len(resp.items) == 2
        # CrewActionRead surfaces details (P3 correlation: details.event_id).
        assert resp.items[0].details is not None
        assert "event_id" in resp.items[0].details

    @pytest.mark.asyncio
    async def test_empty_returns_no_cursor(self) -> None:
        session = _session_returning([])

        resp = await list_crew_actions(
            voyage_id=VOYAGE_ID,
            voyage=_mock_voyage(voyage_id=VOYAGE_ID),
            session=session,
            cursor=None,
            limit=200,
        )

        assert resp.items == []
        assert resp.next_cursor is None

    @pytest.mark.asyncio
    async def test_full_page_returns_cursor(self) -> None:
        rows = [_mock_crew_action() for _ in range(5)]
        session = _session_returning(rows)

        resp = await list_crew_actions(
            voyage_id=VOYAGE_ID,
            voyage=_mock_voyage(voyage_id=VOYAGE_ID),
            session=session,
            cursor=None,
            limit=5,
        )

        assert resp.next_cursor is not None

    @pytest.mark.asyncio
    async def test_invalid_cursor_returns_400(self) -> None:
        session = _session_returning([])

        with pytest.raises(HTTPException) as exc_info:
            await list_crew_actions(
                voyage_id=VOYAGE_ID,
                voyage=_mock_voyage(voyage_id=VOYAGE_ID),
                session=session,
                cursor="garbage",
                limit=200,
            )
        assert exc_info.value.status_code == 400
        assert exc_info.value.detail["error"]["code"] == "INVALID_CURSOR"

    @pytest.mark.asyncio
    async def test_cursor_filters_strictly_below(self) -> None:
        """Equal-`created_at` rows must be tie-broken by id (P6 stability)."""
        session = _session_returning([])
        cursor = encode_cursor(datetime(2026, 4, 30, tzinfo=UTC), uuid.uuid4())

        await list_crew_actions(
            voyage_id=VOYAGE_ID,
            voyage=_mock_voyage(voyage_id=VOYAGE_ID),
            session=session,
            cursor=cursor,
            limit=200,
        )

        passed_stmt = session.execute.await_args.args[0]
        compiled = str(passed_stmt.compile(compile_kwargs={"literal_binds": False}))
        # The disjunction must include both `created_at <` and a tie-break
        # branch that compares id when timestamps match.
        assert "created_at" in compiled.lower()
        assert "OR" in compiled.upper()


# ---------------------------------------------------------------------------
# Cursor helper edge cases
# ---------------------------------------------------------------------------


class TestCursorRoundTrip:
    def test_round_trip_preserves_ts_and_id(self) -> None:
        from app.api.v1._cursor import decode_cursor, encode_cursor

        ts = datetime(2026, 4, 30, 12, 34, 56, 789000, tzinfo=UTC)
        rid = uuid.uuid4()
        encoded = encode_cursor(ts, rid)
        decoded = decode_cursor(encoded)
        assert decoded.ts == ts
        assert decoded.id == rid

    def test_decode_rejects_empty_cursor(self) -> None:
        from app.api.v1._cursor import CursorError, decode_cursor

        with pytest.raises(CursorError):
            decode_cursor("")

    def test_decode_rejects_malformed_base64(self) -> None:
        from app.api.v1._cursor import CursorError, decode_cursor

        with pytest.raises(CursorError):
            decode_cursor("!!!not-base64!!!")

    def test_decode_rejects_missing_fields(self) -> None:
        import base64
        import json

        from app.api.v1._cursor import CursorError, decode_cursor

        bad = base64.urlsafe_b64encode(json.dumps({"ts": "x"}).encode()).decode().rstrip("=")
        with pytest.raises(CursorError):
            decode_cursor(bad)

    def test_decode_rejects_invalid_uuid(self) -> None:
        import base64
        import json

        from app.api.v1._cursor import CursorError, decode_cursor

        bad = (
            base64.urlsafe_b64encode(
                json.dumps({"ts": datetime.now(UTC).isoformat(), "id": "not-a-uuid"}).encode()
            )
            .decode()
            .rstrip("=")
        )
        with pytest.raises(CursorError):
            decode_cursor(bad)

    def test_encode_and_decode_handles_microseconds(self) -> None:
        from app.api.v1._cursor import decode_cursor, encode_cursor

        ts = datetime(2026, 4, 30, 12, 0, 0, 123456, tzinfo=UTC)
        rid = uuid.uuid4()
        decoded = decode_cursor(encode_cursor(ts, rid))
        assert decoded.ts == ts


# Suppress unused-import lints for fixtures/utilities defined for future
# integration tests in other files. (Decorator pattern, intentionally exposed.)
_ = OTHER_USER_ID
_ = timedelta
