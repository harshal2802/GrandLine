"""Tests for the recorded demo script (#56)."""

from __future__ import annotations

import uuid

from app.demo.script import (
    _EVENT_CLASSES,
    DEMO_SCRIPT,
    build_events,
)

VOYAGE_ID = uuid.uuid4()


def test_every_step_has_a_known_event_class() -> None:
    for step in DEMO_SCRIPT:
        assert step.event_type in _EVENT_CLASSES, step.event_type


def test_script_starts_charted_and_ends_completed() -> None:
    assert DEMO_SCRIPT[0].event_type == "pipeline_started"
    last = DEMO_SCRIPT[-1]
    assert last.event_type == "pipeline_completed"
    assert last.stage == "COMPLETED"


def test_all_four_phases_reach_built() -> None:
    final: dict[str, str] = {}
    for step in DEMO_SCRIPT:
        if step.phase_status:
            final.update(step.phase_status)
    assert final == {"1": "BUILT", "2": "BUILT", "3": "BUILT", "4": "BUILT"}


def test_total_runtime_is_under_a_minute() -> None:
    assert sum(s.delay for s in DEMO_SCRIPT) < 60


def test_build_events_emits_log_row_then_typed_event() -> None:
    step = DEMO_SCRIPT[9]  # phase 1 build started
    assert step.event_type == "phase_build_started"
    events = build_events(step, VOYAGE_ID)

    assert len(events) == 2
    crew_action, typed = events
    # Ship's Log row first.
    assert crew_action.event_type == "crew_action_recorded"
    assert crew_action.payload["summary"] == step.summary
    assert crew_action.payload["action_type"] == "phase_build_started"
    assert crew_action.source_role == step.role
    # Typed event last (drives Crew Map + reducer).
    assert typed.event_type == "phase_build_started"
    assert typed.payload["phase_number"] == 1
    assert typed.voyage_id == VOYAGE_ID


def test_stage_entered_carries_voyage_status_payload() -> None:
    step = next(s for s in DEMO_SCRIPT if s.event_type == "pipeline_stage_entered")
    _, typed = build_events(step, VOYAGE_ID)
    assert typed.payload["voyage_status"] == step.stage


def test_deployment_completed_carries_url() -> None:
    step = next(s for s in DEMO_SCRIPT if s.event_type == "deployment_completed")
    _, typed = build_events(step, VOYAGE_ID)
    assert typed.payload["url"].startswith("https://")
    assert typed.payload["tier"] == "preview"
