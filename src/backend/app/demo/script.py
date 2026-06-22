"""The recorded demo voyage — a scripted event timeline (#56).

Mirrors `docs/assets/deck.js` (the GitHub Pages mockup) using the real
`event_type` strings published on `grandline:events:{voyage_id}`. Each step
emits a `crew_action_recorded` (fills the Ship's Log) plus the matching typed
event (pulses the Crew Map and drives the playback reducer's status/phase
chips), so the deck consumes the demo exactly like a live voyage.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.den_den_mushi.events import (
    CodeGeneratedEvent,
    CrewActionRecordedEvent,
    DenDenMushiEvent,
    DeploymentCompletedEvent,
    DeploymentStartedEvent,
    HealthCheckWrittenEvent,
    PhaseBuildFailedEvent,
    PhaseBuildStartedEvent,
    PipelineCompletedEvent,
    PipelineStageEnteredEvent,
    PipelineStartedEvent,
    PoneglyphDraftedEvent,
    TestsPassedEvent,
    ValidationPassedEvent,
    VoyagePlanCreatedEvent,
)
from app.models.enums import CrewRole

# event_type -> typed event class for the events the demo emits.
_EVENT_CLASSES: dict[str, type[DenDenMushiEvent]] = {
    "pipeline_started": PipelineStartedEvent,
    "pipeline_stage_entered": PipelineStageEnteredEvent,
    "voyage_plan_created": VoyagePlanCreatedEvent,
    "poneglyph_drafted": PoneglyphDraftedEvent,
    "health_check_written": HealthCheckWrittenEvent,
    "phase_build_started": PhaseBuildStartedEvent,
    "code_generated": CodeGeneratedEvent,
    "tests_passed": TestsPassedEvent,
    "phase_build_failed": PhaseBuildFailedEvent,
    "validation_passed": ValidationPassedEvent,
    "deployment_started": DeploymentStartedEvent,
    "deployment_completed": DeploymentCompletedEvent,
    "pipeline_completed": PipelineCompletedEvent,
}


@dataclass(frozen=True)
class DemoStep:
    """One beat of the recorded voyage."""

    delay: float  # seconds to pace before this step fires (at 1x speed)
    event_type: str  # typed Den Den Mushi event_type
    role: CrewRole
    summary: str  # Ship's Log line
    stage: str | None = None  # voyage status to set + stage_entered payload
    phase: int | None = None  # phase_number payload (build/test events)
    phase_status: dict[str, str] | None = None  # voyage.phase_status changes after
    extra: dict[str, str] = field(default_factory=dict)  # extra typed payload


def _typed_payload(step: DemoStep) -> dict[str, object]:
    payload: dict[str, object] = dict(step.extra)
    if step.event_type == "pipeline_stage_entered" and step.stage:
        payload["voyage_status"] = step.stage
    if step.phase is not None:
        payload["phase_number"] = step.phase
    return payload


def build_events(step: DemoStep, voyage_id: uuid.UUID) -> list[DenDenMushiEvent]:
    """Events to publish for one step: the Ship's Log row first, then the typed
    event last so the Crew Map's label reflects the typed activity, not the
    raw crew_action_recorded."""
    now = datetime.now(UTC).isoformat()
    details: dict[str, object] = {"demo": True}
    if step.phase is not None:
        details["phase_number"] = step.phase

    crew_action = CrewActionRecordedEvent(
        voyage_id=voyage_id,
        source_role=step.role,
        payload={
            "crew_action_id": str(uuid.uuid4()),
            "event_id": str(uuid.uuid4()),
            "action_type": step.event_type,
            "summary": step.summary,
            "created_at": now,
            "details": details,
        },
    )

    event_cls = _EVENT_CLASSES[step.event_type]
    # Each subclass fixes event_type via a Literal default; mypy only sees the
    # base type[DenDenMushiEvent] whose event_type is required.
    typed = event_cls(  # type: ignore[call-arg]
        voyage_id=voyage_id,
        source_role=step.role,
        payload=_typed_payload(step),
    )
    return [crew_action, typed]


# The recorded voyage: "Build a telemetry pipeline", 4 phases. ~47s at 1x.
DEMO_SCRIPT: list[DemoStep] = [
    DemoStep(
        0.6,
        "pipeline_started",
        CrewRole.CAPTAIN,
        "Voyage accepted — task handed to the Captain",
        stage="PLANNING",
    ),
    DemoStep(
        1.4, "pipeline_stage_entered", CrewRole.CAPTAIN, "Entered stage PLANNING", stage="PLANNING"
    ),
    DemoStep(
        2.6,
        "voyage_plan_created",
        CrewRole.CAPTAIN,
        "Mission decomposed into 4 phases: schema, ingest API, worker, dashboard",
    ),
    DemoStep(1.5, "pipeline_stage_entered", CrewRole.NAVIGATOR, "Entered stage PDD", stage="PDD"),
    DemoStep(
        2.2,
        "poneglyph_drafted",
        CrewRole.NAVIGATOR,
        "Poneglyph drafted for phase 1 — telemetry tables + Alembic migration",
        phase=1,
    ),
    DemoStep(
        1.9,
        "poneglyph_drafted",
        CrewRole.NAVIGATOR,
        "Poneglyphs drafted for phases 2–4 — endpoints, worker, contracts",
    ),
    DemoStep(1.5, "pipeline_stage_entered", CrewRole.DOCTOR, "Entered stage TDD", stage="TDD"),
    DemoStep(
        2.6,
        "health_check_written",
        CrewRole.DOCTOR,
        "12 failing health checks written (pytest) — red as expected, TDD holds",
    ),
    DemoStep(
        1.5,
        "pipeline_stage_entered",
        CrewRole.SHIPWRIGHT,
        "Entered stage BUILDING — 2 parallel Shipwrights on independent phases",
        stage="BUILDING",
    ),
    DemoStep(
        1.2,
        "phase_build_started",
        CrewRole.SHIPWRIGHT,
        "Phase 1 build started on branch agent/shipwright/vg-7f3a2c",
        phase=1,
        phase_status={"1": "BUILDING"},
    ),
    DemoStep(
        2.3,
        "code_generated",
        CrewRole.SHIPWRIGHT,
        "Phase 1 iteration 1 — 6 files generated, running Doctor's checks in sandbox",
        phase=1,
    ),
    DemoStep(
        2.1,
        "tests_passed",
        CrewRole.SHIPWRIGHT,
        "Phase 1 green — 4/4 checks passing, committed to agent branch",
        phase=1,
        phase_status={"1": "BUILT"},
    ),
    DemoStep(
        1.3,
        "phase_build_started",
        CrewRole.SHIPWRIGHT,
        "Phases 2 + 3 build started (parallel layer)",
        phase_status={"2": "BUILDING", "3": "BUILDING"},
    ),
    DemoStep(
        2.4,
        "code_generated",
        CrewRole.SHIPWRIGHT,
        "Phase 2 iteration 1 — 2/5 checks failing, analyzing tracebacks",
        phase=2,
    ),
    DemoStep(
        2.2,
        "code_generated",
        CrewRole.SHIPWRIGHT,
        "Phase 2 iteration 2 — regenerated handler with idempotency key",
        phase=2,
    ),
    DemoStep(
        1.8,
        "tests_passed",
        CrewRole.SHIPWRIGHT,
        "Phase 3 green — worker drains queue in sandbox run",
        phase=3,
        phase_status={"3": "BUILT"},
    ),
    DemoStep(
        1.7,
        "tests_passed",
        CrewRole.SHIPWRIGHT,
        "Phase 2 green on iteration 2 — Vivre Card checkpointed",
        phase=2,
        phase_status={"2": "BUILT"},
    ),
    DemoStep(
        1.3,
        "phase_build_started",
        CrewRole.SHIPWRIGHT,
        "Phase 4 build started — dashboard endpoint",
        phase=4,
        phase_status={"4": "BUILDING"},
    ),
    DemoStep(
        2.4,
        "tests_passed",
        CrewRole.SHIPWRIGHT,
        "Phase 4 green — 12/12 health checks passing overall",
        phase=4,
        phase_status={"4": "BUILT"},
    ),
    DemoStep(
        1.5, "pipeline_stage_entered", CrewRole.DOCTOR, "Entered stage REVIEWING", stage="REVIEWING"
    ),
    DemoStep(
        2.6,
        "validation_passed",
        CrewRole.DOCTOR,
        "Full suite re-run in clean sandbox — 12/12 passing, coverage 91%",
    ),
    DemoStep(
        1.5,
        "pipeline_stage_entered",
        CrewRole.HELMSMAN,
        "Entered stage DEPLOYING",
        stage="DEPLOYING",
    ),
    DemoStep(
        1.6,
        "deployment_started",
        CrewRole.HELMSMAN,
        "Deploying tier=preview ref=agent/shipwright/vg-7f3a2c",
    ),
    DemoStep(
        2.8,
        "deployment_completed",
        CrewRole.HELMSMAN,
        "Preview live — https://preview-vg7f3a.grandline.dev",
        extra={"url": "https://preview-vg7f3a.grandline.dev", "tier": "preview"},
    ),
    DemoStep(
        1.7,
        "pipeline_completed",
        CrewRole.CAPTAIN,
        "Voyage COMPLETED — preview deployed, awaiting fleet admiral for production",
        stage="COMPLETED",
    ),
]
