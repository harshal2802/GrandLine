"""Pipeline transition guards — pure predicates over DB-loaded objects.

Each `require_can_enter_*` helper checks the pre-conditions for entering a
pipeline stage and raises `PipelineError(code, message)` on violation.
Guards perform no I/O (no DB queries, no LLM calls, no events) — the
caller is responsible for loading the voyage plus any artifacts the guard
needs. This also makes them the engine for skip-already-satisfied-stages
on resume: the pipeline calls the next guard; if it passes, the stage is
skipped with no service / LLM call.
"""

from __future__ import annotations

from app.models.build_artifact import BuildArtifact
from app.models.enums import VoyageStatus
from app.models.health_check import HealthCheck
from app.models.poneglyph import Poneglyph
from app.models.validation_run import ValidationRun
from app.models.voyage import Voyage, VoyagePlan
from app.schemas.captain import VoyagePlanSpec
from app.services.shipwright_service import PHASE_STATUS_BUILT

_PLANNABLE_STATUSES = frozenset(
    {VoyageStatus.CHARTED.value, VoyageStatus.PAUSED.value, VoyageStatus.FAILED.value}
)


class PipelineError(Exception):
    """Raised when a pipeline transition pre-condition is violated."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


def _planned_phase_numbers(plan: VoyagePlan) -> list[int]:
    spec = VoyagePlanSpec.model_validate(plan.phases)
    return [p.phase_number for p in spec.phases]


def require_can_enter_planning(voyage: Voyage) -> None:
    """Allow entering PLANNING from CHARTED, PAUSED, or FAILED only."""
    if voyage.status not in _PLANNABLE_STATUSES:
        raise PipelineError(
            "VOYAGE_NOT_PLANNABLE",
            f"Voyage status is {voyage.status}; must be CHARTED, PAUSED, or FAILED",
        )


def require_can_enter_pdd(voyage: Voyage, plan: VoyagePlan | None) -> None:
    """Require a VoyagePlan before entering PDD."""
    if plan is None:
        raise PipelineError("PLAN_MISSING", "Voyage has no plan; Captain must chart first")


def require_can_enter_tdd(voyage: Voyage, plan: VoyagePlan, poneglyphs: list[Poneglyph]) -> None:
    """Every planned phase must have at least one Poneglyph."""
    planned = set(_planned_phase_numbers(plan))
    covered = {p.phase_number for p in poneglyphs} & planned
    missing = planned - covered
    if missing:
        raise PipelineError(
            "PONEGLYPHS_INCOMPLETE",
            f"Phases {sorted(missing)} missing poneglyphs",
        )


def require_can_enter_building(
    voyage: Voyage, plan: VoyagePlan, health_checks: list[HealthCheck]
) -> None:
    """Every planned phase must have at least one HealthCheck."""
    planned = set(_planned_phase_numbers(plan))
    covered = {hc.phase_number for hc in health_checks} & planned
    missing = planned - covered
    if missing:
        raise PipelineError(
            "HEALTH_CHECKS_INCOMPLETE",
            f"Phases {sorted(missing)} missing health_checks",
        )


def require_can_enter_reviewing(
    voyage: Voyage, plan: VoyagePlan, build_artifacts: list[BuildArtifact]
) -> None:
    """Every planned phase must be BUILT with at least one BuildArtifact."""
    planned = set(_planned_phase_numbers(plan))
    with_artifact = {a.phase_number for a in build_artifacts} & planned
    phase_status = voyage.phase_status or {}
    built = {n for n in planned if phase_status.get(str(n)) == PHASE_STATUS_BUILT}
    incomplete = planned - (with_artifact & built)
    if incomplete:
        raise PipelineError(
            "BUILD_INCOMPLETE",
            f"Phases {sorted(incomplete)} not built (missing artifacts or phase_status != BUILT)",
        )


def require_can_enter_deploying(voyage: Voyage, latest_validation: ValidationRun | None) -> None:
    """The most-recent ValidationRun must exist and have status 'passed'."""
    if latest_validation is None or latest_validation.status != "passed":
        raise PipelineError(
            "VALIDATION_NOT_PASSED",
            "Most-recent validation_run must have status 'passed' to deploy",
        )
