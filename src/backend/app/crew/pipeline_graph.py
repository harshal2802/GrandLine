"""Master Voyage Pipeline graph.

Composes the five crew services (Captain → Navigator → Doctor → Shipwright × N
→ Doctor → Helmsman) into a single linear state machine. Each stage node:

1. Re-reads the voyage from DB to detect `PAUSED` / `CANCELLED` between stages.
2. Calls the matching guard from `app.services.pipeline_guards`.
3. Checks skip-already-satisfied (artifacts already exist → no service call).
4. Emits `PipelineStageEnteredEvent`, invokes the crew service, emits
   `PipelineStageCompletedEvent`.
5. Translates any crew-service error into `state["error"]` and routes to
   `fail_end`. On pause, routes to `pause_end`.

Parallel Shipwright: `building_node` runs phases in topological layers,
bounded by `asyncio.Semaphore(max_parallel_shipwrights)`. First failure in a
layer cancels the rest of the layer (fail-fast).
"""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from langgraph.graph import END, StateGraph
from langgraph.graph.state import CompiledStateGraph
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import (
    DenDenMushiEvent,
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStageCompletedEvent,
    PipelineStageEnteredEvent,
)
from app.den_den_mushi.mushi import DenDenMushi
from app.deployment.backend import DeploymentBackend
from app.dial_system.router import DialSystemRouter
from app.models.build_artifact import BuildArtifact
from app.models.deployment import Deployment
from app.models.enums import CrewRole, VoyageStatus
from app.models.health_check import HealthCheck
from app.models.poneglyph import Poneglyph
from app.models.validation_run import ValidationRun
from app.models.vivre_card import VivreCard
from app.models.voyage import Voyage, VoyagePlan
from app.schemas.captain import VoyagePlanSpec
from app.services.captain_service import CaptainError, CaptainService
from app.services.doctor_service import DoctorError, DoctorService
from app.services.execution_service import ExecutionService
from app.services.git_service import GitService
from app.services.helmsman_service import HelmsmanError, HelmsmanService
from app.services.navigator_service import NavigatorError, NavigatorService
from app.services.pipeline_guards import (
    PipelineError,
    require_can_enter_building,
    require_can_enter_deploying,
    require_can_enter_pdd,
    require_can_enter_planning,
    require_can_enter_reviewing,
    require_can_enter_tdd,
)
from app.services.shipwright_service import (
    PHASE_STATUS_BUILT,
    ShipwrightService,
)

logger = logging.getLogger(__name__)

STAGE_PLANNING = "PLANNING"
STAGE_PDD = "PDD"
STAGE_TDD = "TDD"
STAGE_BUILDING = "BUILDING"
STAGE_REVIEWING = "REVIEWING"
STAGE_DEPLOYING = "DEPLOYING"


StageFn = Callable[["PipelineState"], Awaitable[dict[str, Any]]]


class PipelineState(TypedDict):
    voyage_id: uuid.UUID
    user_id: uuid.UUID
    deploy_tier: Literal["preview"]
    max_parallel_shipwrights: int
    task: str
    start_monotonic: float

    plan_id: uuid.UUID | None
    poneglyph_count: int
    health_check_count: int
    build_artifact_count: int
    validation_run_id: uuid.UUID | None
    deployment_id: uuid.UUID | None

    error: dict[str, Any] | None
    paused: bool


@dataclass
class PipelineContext:
    """Dependency container for a single pipeline run.

    Built by `PipelineService.start(...)` and closed over by every stage node.
    Keeping this as a dataclass (rather than the PipelineService itself) keeps
    the graph testable with mocked collaborators.

    `session_factory` is used by `_build_one_phase` to open a per-phase
    `AsyncSession` so parallel Shipwright phases don't share a psycopg
    connection (issue #39). When `None`, the building node falls back to
    the shared `session` — fine for unit tests with mocked sessions, but
    `PipelineService` must always provide a real factory in production.
    """

    session: AsyncSession
    mushi: DenDenMushi
    dial_router: DialSystemRouter
    execution_service: ExecutionService
    git_service: GitService | None
    deployment_backend: DeploymentBackend
    session_factory: async_sessionmaker[AsyncSession] | None = None


def topological_layers(phases: list[dict[str, Any]]) -> list[list[int]]:
    """Return phase numbers grouped into dependency layers.

    Layer N contains phases whose `depends_on` are all in layers < N.
    Raises PipelineError("INVALID_DEP_GRAPH") on cycle. (VoyagePlanSpec already
    rejects cycles at write time; this is defense-in-depth for graph callers.)
    """
    all_phases = {p["phase_number"]: list(p.get("depends_on") or []) for p in phases}
    remaining = dict(all_phases)
    layers: list[list[int]] = []
    completed: set[int] = set()
    while remaining:
        layer = sorted(n for n, deps in remaining.items() if all(d in completed for d in deps))
        if not layer:
            raise PipelineError(
                "INVALID_DEP_GRAPH",
                f"Cycle or unreachable phases in plan: {sorted(remaining)}",
            )
        layers.append(layer)
        completed.update(layer)
        for n in layer:
            del remaining[n]
    return layers


async def _publish(
    mushi: DenDenMushi,
    voyage_id: uuid.UUID,
    event: DenDenMushiEvent,
) -> None:
    """Best-effort publish. Never raises."""
    try:
        await mushi.publish(stream_key(voyage_id), event)
    except Exception:
        logger.warning(
            "Failed to publish %s for voyage %s",
            event.event_type,
            voyage_id,
            exc_info=True,
        )


def _write_vivre_card(
    session: AsyncSession,
    voyage_id: uuid.UUID,
    stage: str,
    reason: str,
    state_data: dict[str, Any],
) -> None:
    card = VivreCard(
        voyage_id=voyage_id,
        crew_member="pipeline",
        state_data={"stage": stage, **state_data},
        checkpoint_reason=reason,
    )
    session.add(card)


async def _load_voyage(session: AsyncSession, voyage_id: uuid.UUID) -> Voyage:
    # `populate_existing=True` bypasses the identity map. Stage nodes call
    # this to observe status / phase_status changes committed by other
    # sessions (issue #39: per-phase Shipwright sessions, the API layer's
    # PAUSED flip, etc.). Without it, the cached instance shadows updates.
    result = await session.execute(
        select(Voyage).where(Voyage.id == voyage_id).execution_options(populate_existing=True)
    )
    return result.scalar_one()


async def _load_plan(session: AsyncSession, voyage_id: uuid.UUID) -> VoyagePlan | None:
    result = await session.execute(
        select(VoyagePlan)
        .where(VoyagePlan.voyage_id == voyage_id)
        .order_by(VoyagePlan.version.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _load_poneglyphs(session: AsyncSession, voyage_id: uuid.UUID) -> list[Poneglyph]:
    result = await session.execute(select(Poneglyph).where(Poneglyph.voyage_id == voyage_id))
    return list(result.scalars().all())


async def _load_health_checks(session: AsyncSession, voyage_id: uuid.UUID) -> list[HealthCheck]:
    result = await session.execute(select(HealthCheck).where(HealthCheck.voyage_id == voyage_id))
    return list(result.scalars().all())


async def _load_build_artifacts(session: AsyncSession, voyage_id: uuid.UUID) -> list[BuildArtifact]:
    result = await session.execute(
        select(BuildArtifact).where(BuildArtifact.voyage_id == voyage_id)
    )
    return list(result.scalars().all())


async def _load_latest_validation(
    session: AsyncSession, voyage_id: uuid.UUID
) -> ValidationRun | None:
    result = await session.execute(
        select(ValidationRun)
        .where(ValidationRun.voyage_id == voyage_id)
        .order_by(ValidationRun.created_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


async def _emit_stage_entered(
    mushi: DenDenMushi, voyage_id: uuid.UUID, stage: str, voyage_status: str
) -> None:
    await _publish(
        mushi,
        voyage_id,
        PipelineStageEnteredEvent(
            voyage_id=voyage_id,
            source_role=CrewRole.CAPTAIN,
            payload={"stage": stage, "voyage_status": voyage_status},
        ),
    )


async def _emit_stage_completed(
    mushi: DenDenMushi,
    voyage_id: uuid.UUID,
    stage: str,
    duration_seconds: float,
    skipped: bool,
) -> None:
    await _publish(
        mushi,
        voyage_id,
        PipelineStageCompletedEvent(
            voyage_id=voyage_id,
            source_role=CrewRole.CAPTAIN,
            payload={
                "stage": stage,
                "duration_seconds": duration_seconds,
                "skipped": skipped,
            },
        ),
    )


# ---------------------------------------------------------------------------
# Stage nodes
# ---------------------------------------------------------------------------


async def _run_stage_with_guard(
    ctx: PipelineContext,
    state: PipelineState,
    stage: str,
    check_paused: bool,
    skip_fn: Callable[[AsyncSession, uuid.UUID], Awaitable[tuple[bool, dict[str, Any]]]],
    run_fn: Callable[[AsyncSession, uuid.UUID], Awaitable[dict[str, Any]]],
    error_types: tuple[type[Exception], ...],
) -> dict[str, Any]:
    voyage_id = state["voyage_id"]
    if check_paused:
        voyage = await _load_voyage(ctx.session, voyage_id)
        if voyage.status == VoyageStatus.PAUSED.value:
            return {"paused": True}
        if voyage.status == VoyageStatus.CANCELLED.value:
            return {
                "error": {
                    "code": "VOYAGE_CANCELLED",
                    "message": "Voyage was cancelled",
                    "stage": stage,
                }
            }

    start = time.monotonic()
    try:
        skipped, skip_update = await skip_fn(ctx.session, voyage_id)
    except PipelineError as exc:
        return {"error": {"code": exc.code, "message": exc.message, "stage": stage}}

    if skipped:
        await _emit_stage_completed(
            ctx.mushi, voyage_id, stage, time.monotonic() - start, skipped=True
        )
        _write_vivre_card(
            ctx.session,
            voyage_id,
            stage,
            "stage_skipped",
            {"skipped": True},
        )
        await ctx.session.commit()
        return skip_update

    voyage = await _load_voyage(ctx.session, voyage_id)
    await _emit_stage_entered(ctx.mushi, voyage_id, stage, voyage.status)
    _write_vivre_card(
        ctx.session, voyage_id, stage, "stage_entered", {"voyage_status": voyage.status}
    )
    await ctx.session.commit()

    try:
        update = await run_fn(ctx.session, voyage_id)
    except error_types as exc:
        code = getattr(exc, "code", exc.__class__.__name__)
        message = getattr(exc, "message", str(exc))
        return {"error": {"code": code, "message": f"{stage}: {message}", "stage": stage}}
    except Exception as exc:
        return {
            "error": {
                "code": "PIPELINE_INTERNAL",
                "message": f"{stage}: {exc.__class__.__name__}: {exc}",
                "stage": stage,
            }
        }

    duration = time.monotonic() - start
    await _emit_stage_completed(ctx.mushi, voyage_id, stage, duration, skipped=False)
    _write_vivre_card(
        ctx.session,
        voyage_id,
        stage,
        "stage_completed",
        {"duration_seconds": duration},
    )
    await ctx.session.commit()
    return update


def _make_planning_node(ctx: PipelineContext) -> StageFn:
    async def node(state: PipelineState) -> dict[str, Any]:
        async def skip(session: AsyncSession, voyage_id: uuid.UUID) -> tuple[bool, dict[str, Any]]:
            voyage = await _load_voyage(session, voyage_id)
            require_can_enter_planning(voyage)
            plan = await _load_plan(session, voyage_id)
            if plan is not None:
                return True, {"plan_id": plan.id}
            return False, {}

        async def run(session: AsyncSession, voyage_id: uuid.UUID) -> dict[str, Any]:
            voyage = await _load_voyage(session, voyage_id)
            captain = CaptainService(ctx.dial_router, ctx.mushi, session)
            plan, _spec = await captain.chart_course(voyage, state["task"])
            return {"plan_id": plan.id}

        return await _run_stage_with_guard(
            ctx, state, STAGE_PLANNING, True, skip, run, (CaptainError,)
        )

    return node


def _make_pdd_node(ctx: PipelineContext) -> StageFn:
    async def node(state: PipelineState) -> dict[str, Any]:
        async def skip(session: AsyncSession, voyage_id: uuid.UUID) -> tuple[bool, dict[str, Any]]:
            voyage = await _load_voyage(session, voyage_id)
            plan = await _load_plan(session, voyage_id)
            require_can_enter_pdd(voyage, plan)
            assert plan is not None  # guarded above
            poneglyphs = await _load_poneglyphs(session, voyage_id)
            try:
                require_can_enter_tdd(voyage, plan, poneglyphs)
            except PipelineError:
                return False, {}
            return True, {"poneglyph_count": len(poneglyphs)}

        async def run(session: AsyncSession, voyage_id: uuid.UUID) -> dict[str, Any]:
            voyage = await _load_voyage(session, voyage_id)
            plan = await _load_plan(session, voyage_id)
            assert plan is not None
            navigator = NavigatorService(ctx.dial_router, ctx.mushi, session)
            poneglyphs = await navigator.draft_poneglyphs(voyage, plan)
            return {"poneglyph_count": len(poneglyphs)}

        return await _run_stage_with_guard(
            ctx, state, STAGE_PDD, True, skip, run, (NavigatorError,)
        )

    return node


def _make_tdd_node(ctx: PipelineContext) -> StageFn:
    async def node(state: PipelineState) -> dict[str, Any]:
        async def skip(session: AsyncSession, voyage_id: uuid.UUID) -> tuple[bool, dict[str, Any]]:
            voyage = await _load_voyage(session, voyage_id)
            plan = await _load_plan(session, voyage_id)
            assert plan is not None
            poneglyphs = await _load_poneglyphs(session, voyage_id)
            require_can_enter_tdd(voyage, plan, poneglyphs)
            health_checks = await _load_health_checks(session, voyage_id)
            try:
                require_can_enter_building(voyage, plan, health_checks)
            except PipelineError:
                return False, {}
            return True, {"health_check_count": len(health_checks)}

        async def run(session: AsyncSession, voyage_id: uuid.UUID) -> dict[str, Any]:
            voyage = await _load_voyage(session, voyage_id)
            poneglyphs = await _load_poneglyphs(session, voyage_id)
            doctor = DoctorService(
                ctx.dial_router, ctx.mushi, session, ctx.execution_service, ctx.git_service
            )
            health_checks = await doctor.write_health_checks(voyage, poneglyphs, state["user_id"])
            return {"health_check_count": len(health_checks)}

        return await _run_stage_with_guard(ctx, state, STAGE_TDD, True, skip, run, (DoctorError,))

    return node


async def _build_one_phase(
    ctx: PipelineContext,
    state: PipelineState,
    phase_number: int,
    poneglyph: Poneglyph,
    health_checks: list[HealthCheck],
    semaphore: asyncio.Semaphore,
) -> None:
    async with semaphore:
        # Issue #39: parallel phases must not share a psycopg connection.
        # In production, ctx.session_factory is always set; fall back to the
        # shared session only for unit tests with mocked sessions.
        if ctx.session_factory is not None:
            async with ctx.session_factory() as phase_session:
                voyage = await _load_voyage(phase_session, state["voyage_id"])
                shipwright = ShipwrightService(
                    ctx.dial_router,
                    ctx.mushi,
                    phase_session,
                    ctx.execution_service,
                    ctx.git_service,
                )
                await shipwright.build_code(
                    voyage, phase_number, poneglyph, health_checks, state["user_id"]
                )
        else:
            voyage = await _load_voyage(ctx.session, state["voyage_id"])
            shipwright = ShipwrightService(
                ctx.dial_router, ctx.mushi, ctx.session, ctx.execution_service, ctx.git_service
            )
            await shipwright.build_code(
                voyage, phase_number, poneglyph, health_checks, state["user_id"]
            )


def _make_building_node(ctx: PipelineContext) -> StageFn:
    async def node(state: PipelineState) -> dict[str, Any]:
        voyage_id = state["voyage_id"]
        voyage = await _load_voyage(ctx.session, voyage_id)
        if voyage.status == VoyageStatus.PAUSED.value:
            return {"paused": True}

        plan = await _load_plan(ctx.session, voyage_id)
        assert plan is not None
        health_checks = await _load_health_checks(ctx.session, voyage_id)
        try:
            require_can_enter_building(voyage, plan, health_checks)
        except PipelineError as exc:
            return {"error": {"code": exc.code, "message": exc.message, "stage": STAGE_BUILDING}}

        artifacts = await _load_build_artifacts(ctx.session, voyage_id)
        try:
            require_can_enter_reviewing(voyage, plan, artifacts)
            start = time.monotonic()
            await _emit_stage_completed(
                ctx.mushi, voyage_id, STAGE_BUILDING, time.monotonic() - start, skipped=True
            )
            return {"build_artifact_count": len(artifacts)}
        except PipelineError:
            pass

        spec = VoyagePlanSpec.model_validate(plan.phases)
        phases_by_num = {p.phase_number: p for p in spec.phases}
        poneglyph_by_phase = {
            p.phase_number: p for p in await _load_poneglyphs(ctx.session, voyage_id)
        }
        hc_by_phase: dict[int, list[HealthCheck]] = {}
        for hc in health_checks:
            hc_by_phase.setdefault(hc.phase_number, []).append(hc)

        phase_dicts = [
            {"phase_number": n, "depends_on": p.depends_on} for n, p in phases_by_num.items()
        ]
        try:
            layers = topological_layers(phase_dicts)
        except PipelineError as exc:
            return {"error": {"code": exc.code, "message": exc.message, "stage": STAGE_BUILDING}}

        semaphore = asyncio.Semaphore(state["max_parallel_shipwrights"])

        await _emit_stage_entered(ctx.mushi, voyage_id, STAGE_BUILDING, voyage.status)
        _write_vivre_card(
            ctx.session,
            voyage_id,
            STAGE_BUILDING,
            "stage_entered",
            {"voyage_status": voyage.status},
        )
        await ctx.session.commit()

        start = time.monotonic()
        for layer in layers:
            # Fetch phase_status once per layer — Shipwright builds within the
            # layer run under the same voyage row, and we want the pre-layer
            # snapshot to decide what to schedule.
            current_voyage = await _load_voyage(ctx.session, voyage_id)
            phase_status_map = dict(current_voyage.phase_status or {})
            pending = [n for n in layer if phase_status_map.get(str(n)) != PHASE_STATUS_BUILT]
            if not pending:
                continue
            tasks = [
                asyncio.create_task(
                    _build_one_phase(
                        ctx, state, n, poneglyph_by_phase[n], hc_by_phase.get(n, []), semaphore
                    )
                )
                for n in pending
            ]
            try:
                await asyncio.gather(*tasks)
            except Exception as exc:
                for t in tasks:
                    if not t.done():
                        t.cancel()
                # Drain cancelled tasks so we don't leak pending coroutines.
                await asyncio.gather(*tasks, return_exceptions=True)
                code = getattr(exc, "code", exc.__class__.__name__)
                message = getattr(exc, "message", str(exc))
                return {
                    "error": {
                        "code": code,
                        "message": f"{STAGE_BUILDING}: {message}",
                        "stage": STAGE_BUILDING,
                    }
                }

        duration = time.monotonic() - start
        await _emit_stage_completed(ctx.mushi, voyage_id, STAGE_BUILDING, duration, skipped=False)
        _write_vivre_card(
            ctx.session,
            voyage_id,
            STAGE_BUILDING,
            "stage_completed",
            {"duration_seconds": duration},
        )
        await ctx.session.commit()
        final_artifacts = await _load_build_artifacts(ctx.session, voyage_id)
        return {"build_artifact_count": len(final_artifacts)}

    return node


def _make_reviewing_node(ctx: PipelineContext) -> StageFn:
    async def node(state: PipelineState) -> dict[str, Any]:
        async def skip(session: AsyncSession, voyage_id: uuid.UUID) -> tuple[bool, dict[str, Any]]:
            voyage = await _load_voyage(session, voyage_id)
            plan = await _load_plan(session, voyage_id)
            assert plan is not None
            artifacts = await _load_build_artifacts(session, voyage_id)
            require_can_enter_reviewing(voyage, plan, artifacts)
            latest = await _load_latest_validation(session, voyage_id)
            if latest is not None and latest.status == "passed":
                return True, {"validation_run_id": latest.id}
            return False, {}

        async def run(session: AsyncSession, voyage_id: uuid.UUID) -> dict[str, Any]:
            voyage = await _load_voyage(session, voyage_id)
            artifacts = await _load_build_artifacts(session, voyage_id)
            shipwright_files = {a.file_path: a.content for a in artifacts}
            doctor = DoctorService(
                ctx.dial_router, ctx.mushi, session, ctx.execution_service, ctx.git_service
            )
            await doctor.validate_code(voyage, state["user_id"], shipwright_files)
            latest = await _load_latest_validation(session, voyage_id)
            if latest is None or latest.status != "passed":
                # Raise PipelineError here (not DoctorError) because validate_code
                # persists a ValidationRun even on failure, so the failure mode is
                # a pipeline-level outcome rather than a Doctor-service exception.
                # _run_stage_with_guard treats this uniformly via error_types.
                raise PipelineError(
                    "VALIDATION_FAILED", "Validation did not pass — see ValidationRun"
                )
            return {"validation_run_id": latest.id}

        return await _run_stage_with_guard(
            ctx, state, STAGE_REVIEWING, True, skip, run, (DoctorError, PipelineError)
        )

    return node


def _make_deploying_node(ctx: PipelineContext) -> StageFn:
    async def node(state: PipelineState) -> dict[str, Any]:
        async def skip(session: AsyncSession, voyage_id: uuid.UUID) -> tuple[bool, dict[str, Any]]:
            latest_validation = await _load_latest_validation(session, voyage_id)
            require_can_enter_deploying(await _load_voyage(session, voyage_id), latest_validation)
            return False, {}

        async def run(session: AsyncSession, voyage_id: uuid.UUID) -> dict[str, Any]:
            voyage = await _load_voyage(session, voyage_id)
            helmsman = HelmsmanService(
                ctx.dial_router, ctx.mushi, session, ctx.deployment_backend, ctx.git_service
            )
            deployment = await helmsman.deploy(voyage, state["deploy_tier"], state["user_id"])
            return {"deployment_id": deployment.deployment_id}

        return await _run_stage_with_guard(
            ctx, state, STAGE_DEPLOYING, True, skip, run, (HelmsmanError,)
        )

    return node


def _make_finalize_node(ctx: PipelineContext) -> StageFn:
    async def node(state: PipelineState) -> dict[str, Any]:
        voyage_id = state["voyage_id"]
        voyage = await _load_voyage(ctx.session, voyage_id)
        voyage.status = VoyageStatus.COMPLETED.value
        ctx.session.add(voyage)
        _write_vivre_card(ctx.session, voyage_id, "FINALIZE", "pipeline_completed", {})
        await ctx.session.commit()

        deployment_url: str | None = None
        dep_id = state.get("deployment_id")
        if dep_id is not None:
            result = await ctx.session.execute(select(Deployment).where(Deployment.id == dep_id))
            dep = result.scalar_one_or_none()
            if dep is not None:
                deployment_url = dep.url

        start = state.get("start_monotonic", time.monotonic())
        duration = max(0.0, time.monotonic() - start)

        await _publish(
            ctx.mushi,
            voyage_id,
            PipelineCompletedEvent(
                voyage_id=voyage_id,
                source_role=CrewRole.CAPTAIN,
                payload={
                    "duration_seconds": duration,
                    "deployment_url": deployment_url,
                },
            ),
        )
        return {}

    return node


def _make_fail_end(ctx: PipelineContext) -> StageFn:
    async def node(state: PipelineState) -> dict[str, Any]:
        voyage_id = state["voyage_id"]
        voyage = await _load_voyage(ctx.session, voyage_id)
        voyage.status = VoyageStatus.FAILED.value
        ctx.session.add(voyage)
        err = state.get("error") or {"code": "UNKNOWN", "message": "", "stage": "UNKNOWN"}
        _write_vivre_card(
            ctx.session, voyage_id, err.get("stage", "UNKNOWN"), "pipeline_failed", err
        )
        await ctx.session.commit()
        await _publish(
            ctx.mushi,
            voyage_id,
            PipelineFailedEvent(
                voyage_id=voyage_id,
                source_role=CrewRole.CAPTAIN,
                payload={
                    "stage": err.get("stage", "UNKNOWN"),
                    "code": err.get("code", "UNKNOWN"),
                    "message": err.get("message", ""),
                },
            ),
        )
        return {}

    return node


def _make_pause_end(ctx: PipelineContext) -> StageFn:
    async def node(_state: PipelineState) -> dict[str, Any]:
        return {}

    return node


def _route_after_stage(state: PipelineState, next_stage: str) -> str:
    if state.get("paused"):
        return "pause_end"
    if state.get("error"):
        return "fail_end"
    return next_stage


def build_pipeline_graph(ctx: PipelineContext) -> CompiledStateGraph:  # type: ignore[type-arg]
    # LangGraph's `StateGraph(PipelineState)` doesn't propagate the state type
    # through add_node's Protocol shape, so each add_node call needs an ignore.
    graph = StateGraph(PipelineState)

    graph.add_node("planning", _make_planning_node(ctx))  # type: ignore[call-overload]
    graph.add_node("pdd", _make_pdd_node(ctx))  # type: ignore[call-overload]
    graph.add_node("tdd", _make_tdd_node(ctx))  # type: ignore[call-overload]
    graph.add_node("building", _make_building_node(ctx))  # type: ignore[call-overload]
    graph.add_node("reviewing", _make_reviewing_node(ctx))  # type: ignore[call-overload]
    graph.add_node("deploying", _make_deploying_node(ctx))  # type: ignore[call-overload]
    graph.add_node("finalize", _make_finalize_node(ctx))  # type: ignore[call-overload]
    graph.add_node("fail_end", _make_fail_end(ctx))  # type: ignore[call-overload]
    graph.add_node("pause_end", _make_pause_end(ctx))  # type: ignore[call-overload]

    graph.set_entry_point("planning")

    for stage, next_stage in [
        ("planning", "pdd"),
        ("pdd", "tdd"),
        ("tdd", "building"),
        ("building", "reviewing"),
        ("reviewing", "deploying"),
        ("deploying", "finalize"),
    ]:
        graph.add_conditional_edges(
            stage,
            lambda s, ns=next_stage: _route_after_stage(s, ns),
            {"pause_end": "pause_end", "fail_end": "fail_end", next_stage: next_stage},
        )

    graph.add_edge("finalize", END)
    graph.add_edge("fail_end", END)
    graph.add_edge("pause_end", END)

    return graph.compile()


__all__ = [
    "PipelineContext",
    "PipelineState",
    "STAGE_BUILDING",
    "STAGE_DEPLOYING",
    "STAGE_PDD",
    "STAGE_PLANNING",
    "STAGE_REVIEWING",
    "STAGE_TDD",
    "build_pipeline_graph",
    "topological_layers",
]
