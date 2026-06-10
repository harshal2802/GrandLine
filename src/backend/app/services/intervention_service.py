"""Intervention drain — feeds pending user interventions into the running pipeline.

Phase 17 follow-up (#51). `POST /voyages/{id}/inject` and `/redirect` persist a
durable `CrewAction` (CONTEXT_INJECTED / PHASE_REDIRECTED) but, until now, nothing
consumed those rows — the active agent's next LLM call never saw the injected
context and a redirected phase kept its original Poneglyph instruction.

A crew node calls `drain_pending_interventions(...)` before composing its prompt.
Each consumed intervention is stamped (`details.applied_phases` gains the phase
number, `details.applied_at` records first consumption) so it is applied to a
given phase exactly once — even across the Shipwright's retry iterations.

Targeting:
  * CONTEXT_INJECTED with `phase_number == N` reaches phase N; a global inject
    (`phase_number is None`) reaches every phase, once each.
  * PHASE_REDIRECTED with `phase_number == N` reaches phase N only.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.crew_action import CrewAction
from app.services.crew_action_helper import CrewActionType

_INTERVENTION_TYPES = (
    CrewActionType.CONTEXT_INJECTED.value,
    CrewActionType.PHASE_REDIRECTED.value,
)


@dataclass
class DrainedInterventions:
    """Interventions consumed for one phase on one drain."""

    injected_context: list[str] = field(default_factory=list)
    redirect_instruction: str | None = None
    applied_actions: list[CrewAction] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.injected_context and self.redirect_instruction is None


async def drain_pending_interventions(
    session: AsyncSession, voyage_id: uuid.UUID, phase_number: int
) -> DrainedInterventions:
    """Consume interventions targeting `phase_number` not yet applied to it.

    Marks each consumed CrewAction so it is not re-applied to the same phase,
    then flushes (durability is the caller's commit). Returns the injected
    context strings in record order and the latest redirect instruction.
    """
    rows = (
        (
            await session.execute(
                select(CrewAction)
                .where(
                    CrewAction.voyage_id == voyage_id,
                    CrewAction.action_type.in_(_INTERVENTION_TYPES),
                )
                .order_by(CrewAction.created_at.asc(), CrewAction.id.asc())
            )
        )
        .scalars()
        .all()
    )

    drained = DrainedInterventions()
    now = datetime.now(UTC).isoformat()

    for action in rows:
        details = dict(action.details or {})
        applied_phases = list(details.get("applied_phases") or [])
        if phase_number in applied_phases:
            continue

        target = details.get("phase_number")
        if action.action_type == CrewActionType.CONTEXT_INJECTED.value:
            if target is not None and target != phase_number:
                continue
            context = details.get("context")
            if context:
                drained.injected_context.append(str(context))
        elif action.action_type == CrewActionType.PHASE_REDIRECTED.value:
            if target != phase_number:
                continue
            instruction = details.get("instruction")
            if instruction:
                drained.redirect_instruction = str(instruction)
        else:  # pragma: no cover - query is filtered to the two types above
            continue

        applied_phases.append(phase_number)
        details["applied_phases"] = applied_phases
        details.setdefault("applied_at", now)
        # Reassign (not mutate) so SQLAlchemy marks the JSONB column dirty.
        action.details = details
        drained.applied_actions.append(action)

    if drained.applied_actions:
        await session.flush()

    return drained


__all__ = ["DrainedInterventions", "drain_pending_interventions"]
