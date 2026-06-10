"""Tests for the intervention drain (#51)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.crew_action import CrewAction
from app.services.crew_action_helper import CrewActionType
from app.services.intervention_service import drain_pending_interventions

VOYAGE_ID = uuid.uuid4()


def _action(action_type: CrewActionType, details: dict[str, Any]) -> CrewAction:
    return CrewAction(
        id=uuid.uuid4(),
        voyage_id=VOYAGE_ID,
        crew_member="captain",
        action_type=action_type.value,
        summary="x",
        details=details,
    )


def _session(actions: list[CrewAction]) -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    result = MagicMock()
    result.scalars.return_value.all.return_value = actions
    session.execute = AsyncMock(return_value=result)
    return session


@pytest.mark.asyncio
async def test_empty_when_no_interventions() -> None:
    session = _session([])
    drained = await drain_pending_interventions(session, VOYAGE_ID, 1)
    assert drained.is_empty
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
async def test_phase_targeted_inject_reaches_matching_phase() -> None:
    action = _action(CrewActionType.CONTEXT_INJECTED, {"context": "use redis", "phase_number": 1})
    session = _session([action])

    drained = await drain_pending_interventions(session, VOYAGE_ID, 1)

    assert drained.injected_context == ["use redis"]
    assert 1 in action.details["applied_phases"]
    assert "applied_at" in action.details
    session.flush.assert_awaited_once()


@pytest.mark.asyncio
async def test_phase_targeted_inject_skipped_for_other_phase() -> None:
    action = _action(CrewActionType.CONTEXT_INJECTED, {"context": "use redis", "phase_number": 2})
    session = _session([action])

    drained = await drain_pending_interventions(session, VOYAGE_ID, 1)

    assert drained.injected_context == []
    assert "applied_phases" not in action.details


@pytest.mark.asyncio
async def test_global_inject_reaches_any_phase() -> None:
    action = _action(
        CrewActionType.CONTEXT_INJECTED, {"context": "prefer postgres", "phase_number": None}
    )
    session = _session([action])

    drained = await drain_pending_interventions(session, VOYAGE_ID, 7)

    assert drained.injected_context == ["prefer postgres"]
    assert action.details["applied_phases"] == [7]


@pytest.mark.asyncio
async def test_global_inject_applied_once_per_phase() -> None:
    action = _action(
        CrewActionType.CONTEXT_INJECTED, {"context": "global note", "phase_number": None}
    )
    session = _session([action])

    first = await drain_pending_interventions(session, VOYAGE_ID, 1)
    # Same row, now marked applied for phase 1; draining phase 1 again is a no-op.
    second = await drain_pending_interventions(session, VOYAGE_ID, 1)
    # A different phase still sees it.
    third = await drain_pending_interventions(session, VOYAGE_ID, 2)

    assert first.injected_context == ["global note"]
    assert second.injected_context == []
    assert third.injected_context == ["global note"]
    assert action.details["applied_phases"] == [1, 2]


@pytest.mark.asyncio
async def test_redirect_reaches_matching_phase_only() -> None:
    action = _action(
        CrewActionType.PHASE_REDIRECTED, {"instruction": "use a state machine", "phase_number": 3}
    )
    session = _session([action])

    match = await drain_pending_interventions(session, VOYAGE_ID, 3)
    other = await drain_pending_interventions(_session([action]), VOYAGE_ID, 4)

    assert match.redirect_instruction == "use a state machine"
    assert other.redirect_instruction is None


@pytest.mark.asyncio
async def test_latest_redirect_wins() -> None:
    first = _action(
        CrewActionType.PHASE_REDIRECTED, {"instruction": "approach A", "phase_number": 1}
    )
    second = _action(
        CrewActionType.PHASE_REDIRECTED, {"instruction": "approach B", "phase_number": 1}
    )
    session = _session([first, second])

    drained = await drain_pending_interventions(session, VOYAGE_ID, 1)

    assert drained.redirect_instruction == "approach B"


@pytest.mark.asyncio
async def test_already_applied_not_redrained() -> None:
    action = _action(
        CrewActionType.CONTEXT_INJECTED,
        {"context": "old", "phase_number": 1, "applied_phases": [1], "applied_at": "t"},
    )
    session = _session([action])

    drained = await drain_pending_interventions(session, VOYAGE_ID, 1)

    assert drained.is_empty
    session.flush.assert_not_awaited()
