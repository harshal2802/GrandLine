"""CrewAction helper — durable per-checkpoint records for the Ship's Log.

Phase 16.0 deliverable. The crew_actions table already exists; this module
provides the small write-helper that crew services use to append a row to
their open transaction, plus the post-commit best-effort event-publish
helper.

Contracts respected:
- P3 (event_id correlation): every row carries `details["event_id"]` so a
  later `crew_action_recorded` event can be deduped against the row.
- P8 (locked taxonomy): `action_type` is the `CrewActionType` enum below;
  ad-hoc strings are rejected.
- P13 (canonical timestamp): `created_at` is the DB column, surfaced in
  the published event payload.
"""

from __future__ import annotations

import enum
import logging
import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import CrewActionRecordedEvent
from app.den_den_mushi.mushi import DenDenMushi
from app.models.crew_action import CrewAction
from app.models.enums import CrewRole

logger = logging.getLogger(__name__)

_SUMMARY_MAX = 200


class CrewActionType(str, enum.Enum):
    """Locked taxonomy for crew_actions.action_type (P8)."""

    PLAN_CREATED = "plan_created"
    PONEGLYPH_DRAFTED = "poneglyph_drafted"
    HEALTH_CHECK_WRITTEN = "health_check_written"
    PHASE_BUILD_STARTED = "phase_build_started"
    PHASE_BUILD_COMPLETED = "phase_build_completed"
    PHASE_BUILD_FAILED = "phase_build_failed"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    DEPLOYMENT_STARTED = "deployment_started"
    DEPLOYMENT_COMPLETED = "deployment_completed"
    DEPLOYMENT_FAILED = "deployment_failed"
    PIPELINE_PAUSED = "pipeline_paused"
    PIPELINE_RESUMED = "pipeline_resumed"
    PIPELINE_CANCELLED = "pipeline_cancelled"
    PIPELINE_FAILED = "pipeline_failed"
    PIPELINE_COMPLETED = "pipeline_completed"
    # User interventions (Phase 17).
    CONTEXT_INJECTED = "context_injected"
    PHASE_REDIRECTED = "phase_redirected"
    # Bedside Browser (Phase 23) — Doctor browser-in-the-loop verification.
    BROWSER_CHECK_RUN = "browser_check_run"


def record_action(
    session: AsyncSession,
    voyage_id: uuid.UUID,
    crew_member: CrewRole,
    action_type: CrewActionType,
    summary: str,
    details: dict[str, Any] | None = None,
) -> CrewAction:
    """Append a CrewAction row to the caller's open transaction.

    The action is part of the same `AsyncSession` the caller is using —
    failure of the action's commit rolls back the entire service operation
    along with it. The helper does NOT commit on its own.

    A unique `event_id` is generated and merged into `details["event_id"]`
    so the frontend can dedupe a CrewActionRecordedEvent (P3 correlation
    rule). Returns the unflushed CrewAction so callers can await
    `session.flush()` if they need the row's `id` or `created_at`.

    Raises:
        ValueError: when `summary` exceeds 200 chars.
        TypeError: when `action_type` is not a CrewActionType (P8).
        ValueError: when caller-provided `details` already has `event_id`.
    """
    if not isinstance(action_type, CrewActionType):
        raise TypeError(f"action_type must be a CrewActionType, got {type(action_type).__name__}")

    if len(summary) > _SUMMARY_MAX:
        raise ValueError(f"summary must be <= {_SUMMARY_MAX} chars (got {len(summary)})")

    merged: dict[str, Any] = dict(details) if details else {}
    if "event_id" in merged:
        raise ValueError("details must not pre-set 'event_id'; record_action generates it")
    merged["event_id"] = str(uuid.uuid4())

    action = CrewAction(
        voyage_id=voyage_id,
        crew_member=crew_member.value,
        action_type=action_type.value,
        summary=summary,
        details=merged,
    )
    session.add(action)
    return action


async def publish_crew_action_recorded(
    mushi: DenDenMushi,
    voyage_id: uuid.UUID,
    crew_action: CrewAction,
) -> None:
    """Best-effort post-commit publish of a `crew_action_recorded` event.

    Callers invoke this after `session.commit()` succeeds. A failure to
    publish does NOT roll back — the durable record is the DB row.

    Payload contract (P13 canonical timestamp; P3 correlation):
      {
        "crew_action_id": str (UUID),
        "event_id": str (UUID; matches details.event_id),
        "action_type": str,
        "summary": str,
        "created_at": str (ISO8601),
        "details": dict,
      }
    """
    details = crew_action.details or {}
    event_id_str = details.get("event_id")

    payload: dict[str, Any] = {
        "crew_action_id": str(crew_action.id),
        "event_id": event_id_str,
        "action_type": crew_action.action_type,
        "summary": crew_action.summary,
        "created_at": crew_action.created_at.isoformat() if crew_action.created_at else None,
        "details": dict(details),
    }

    try:
        crew_role = CrewRole(crew_action.crew_member)
    except ValueError:
        # Defensive — crew_member should always be a CrewRole value, but the
        # column is plain string. Fall back to CAPTAIN to keep the event
        # publishable rather than silently dropping the post-commit emit.
        logger.warning(
            "crew_action %s has unknown crew_member %r; defaulting to CAPTAIN",
            crew_action.id,
            crew_action.crew_member,
        )
        crew_role = CrewRole.CAPTAIN

    event = CrewActionRecordedEvent(
        voyage_id=voyage_id,
        source_role=crew_role,
        payload=payload,
    )

    try:
        await mushi.publish(stream_key(voyage_id), event)
    except Exception:
        logger.warning(
            "Failed to publish crew_action_recorded event for voyage %s (action %s)",
            voyage_id,
            crew_action.id,
            exc_info=True,
        )


__all__ = [
    "CrewActionType",
    "publish_crew_action_recorded",
    "record_action",
]
