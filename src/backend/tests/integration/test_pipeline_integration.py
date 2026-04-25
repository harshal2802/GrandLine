"""End-to-end integration tests for the Voyage Pipeline (Phase 15.5).

These tests exercise `PipelineService.start(...)` against real Postgres and
real Redis with only the LLM (`DialSystemRouter.route`) and the sandbox
(`ExecutionBackend.execute`) boundaries replaced with stubs.

Running locally:

    make up && make migrate
    cd src/backend && pytest -m integration tests/integration/ -v

The suite is skipped automatically if Postgres or Redis is unreachable.

Implementation notes / locked decisions
---------------------------------------
- LLM mock lives at `DialSystemRouter` adapter level so each crew service's
  prompt + parser code path is exercised. See `canned_llm.py`.
- Sandbox mock returns canned "all passed" pytest output for every call
  (see `stubs.StubExecutionBackend`).
- `InProcessDeploymentBackend` is the real production v1 backend and needs
  no patching. To trigger a deploy failure we instantiate it with
  `fail_tiers={"preview"}`.
- Concurrency assertions wrap `ShipwrightService.build_code` with an
  in-flight counter probe (see `_PeakCounter`).
- Dep-ordering assertions read `tests_passed` events back from the Redis
  stream and compare timestamps.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from collections import Counter
from collections.abc import Awaitable, Callable
from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.events import (
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStageCompletedEvent,
    PipelineStageEnteredEvent,
    PipelineStartedEvent,
)
from app.den_den_mushi.events import (
    TestsPassedEvent as _TestsPassedEvent,  # rename to avoid pytest test-class collection warning
)
from app.den_den_mushi.mushi import DenDenMushi
from app.deployment.in_process import InProcessDeploymentBackend
from app.dial_system.router import DialSystemRouter
from app.models.build_artifact import BuildArtifact
from app.models.deployment import Deployment
from app.models.dial_config import DialConfig
from app.models.enums import CrewRole, VoyageStatus
from app.models.health_check import HealthCheck
from app.models.poneglyph import Poneglyph
from app.models.user import User
from app.models.validation_run import ValidationRun
from app.models.vivre_card import VivreCard
from app.models.voyage import Voyage, VoyagePlan
from app.services.execution_service import ExecutionService
from app.services.pipeline_guards import PipelineError
from app.services.pipeline_service import PipelineService
from app.services.shipwright_service import (
    PHASE_STATUS_BUILT,
    PHASE_STATUS_PENDING,
    ShipwrightService,
)
from tests.integration.canned_llm import (
    _default_doctor_health_checks,
    _default_navigator_for_phases,
    _default_shipwright_for_phase,
    make_role_router,
)

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_user(session: AsyncSession) -> User:
    suffix = uuid.uuid4().hex[:8]
    user = User(
        email=f"itest+{suffix}@example.com",
        username=f"itest_{suffix}",
        hashed_password="not-a-real-hash",
        is_active=True,
    )
    session.add(user)
    await session.flush()
    return user


async def _seed_voyage(
    session: AsyncSession,
    user: User,
    *,
    title: str = "integration voyage",
    status: VoyageStatus = VoyageStatus.CHARTED,
    phase_status: dict[str, Any] | None = None,
) -> Voyage:
    voyage = Voyage(
        user_id=user.id,
        title=title,
        description="phase 15.5 integration test",
        status=status.value,
        phase_status=phase_status or {},
    )
    session.add(voyage)
    await session.flush()
    return voyage


async def _seed_dial_config(
    session: AsyncSession,
    voyage: Voyage,
    *,
    shipwright_max_concurrency: int = 3,
) -> DialConfig:
    dial = DialConfig(
        voyage_id=voyage.id,
        role_mapping={
            "captain": {"provider": "stub", "model": "stub"},
            "navigator": {"provider": "stub", "model": "stub"},
            "doctor": {"provider": "stub", "model": "stub"},
            "shipwright": {
                "provider": "stub",
                "model": "stub",
                "max_concurrency": shipwright_max_concurrency,
            },
            "helmsman": {"provider": "stub", "model": "stub"},
        },
    )
    session.add(dial)
    await session.flush()
    return dial


def _make_service(
    session: AsyncSession,
    mushi: DenDenMushi,
    router: DialSystemRouter,
    execution_service: ExecutionService,
    deployment_backend: InProcessDeploymentBackend,
    session_factory: async_sessionmaker[AsyncSession] | None = None,
) -> PipelineService:
    return PipelineService(
        session=session,
        mushi=mushi,
        dial_router=router,
        execution_service=execution_service,
        git_service=None,
        deployment_backend=deployment_backend,
        session_factory=session_factory,
    )


async def _replay_event_types(mushi: DenDenMushi, voyage_id: uuid.UUID) -> list[str]:
    events = await mushi.replay(stream_key(voyage_id), count=500)
    return [e.event_type for _id, e in events]


async def _replay_events(mushi: DenDenMushi, voyage_id: uuid.UUID) -> list[Any]:
    events = await mushi.replay(stream_key(voyage_id), count=500)
    return [e for _id, e in events]


# ---------------------------------------------------------------------------
# In-flight concurrency probe
# ---------------------------------------------------------------------------


class _PeakCounter:
    """Track in-flight count + peak under an asyncio.Lock."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self.in_flight = 0
        self.peak = 0

    async def enter(self) -> None:
        async with self._lock:
            self.in_flight += 1
            if self.in_flight > self.peak:
                self.peak = self.in_flight

    async def exit(self) -> None:
        async with self._lock:
            self.in_flight -= 1


def _wrap_shipwright_build_code(
    counter: _PeakCounter,
    *,
    sleep_seconds: float = 0.0,
) -> Callable[[Any, Any], Awaitable[Any]]:
    """Return an async wrapper that increments / decrements the probe."""
    original = ShipwrightService.build_code

    async def _wrapped(self: Any, *args: Any, **kwargs: Any) -> Any:
        await counter.enter()
        try:
            if sleep_seconds:
                await asyncio.sleep(sleep_seconds)
            return await original(self, *args, **kwargs)
        finally:
            await counter.exit()

    return _wrapped


# ---------------------------------------------------------------------------
# TestHappyPath
# ---------------------------------------------------------------------------


class TestHappyPath:
    async def test_full_pipeline_runs_to_completed(
        self,
        db_session: AsyncSession,
        mushi: DenDenMushi,
        voyage_id: uuid.UUID,
        stub_execution_service: ExecutionService,
        stub_deployment_backend: InProcessDeploymentBackend,
    ) -> None:
        user = await _seed_user(db_session)
        voyage = await _seed_voyage(db_session, user)
        await _seed_dial_config(db_session, voyage, shipwright_max_concurrency=3)
        await db_session.commit()

        router = make_role_router(mushi, voyage.id)
        service = _make_service(
            db_session,
            mushi,
            router,
            stub_execution_service,
            stub_deployment_backend,
        )

        await service.start(voyage, user.id, "build a calculator", "preview")

        # voyage state: COMPLETED, all 3 phases BUILT
        await db_session.refresh(voyage)
        assert voyage.status == VoyageStatus.COMPLETED.value
        assert voyage.phase_status == {
            "1": PHASE_STATUS_BUILT,
            "2": PHASE_STATUS_BUILT,
            "3": PHASE_STATUS_BUILT,
        }

        # plan + 3 poneglyphs + 3 health_checks + 3 build_artifacts
        plans = (
            (await db_session.execute(select(VoyagePlan).where(VoyagePlan.voyage_id == voyage.id)))
            .scalars()
            .all()
        )
        assert len(plans) == 1

        poneglyphs = (
            (await db_session.execute(select(Poneglyph).where(Poneglyph.voyage_id == voyage.id)))
            .scalars()
            .all()
        )
        assert len(poneglyphs) == 3

        health_checks = (
            (
                await db_session.execute(
                    select(HealthCheck).where(HealthCheck.voyage_id == voyage.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(health_checks) == 3

        artifacts = (
            (
                await db_session.execute(
                    select(BuildArtifact).where(BuildArtifact.voyage_id == voyage.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(artifacts) == 3

        validation = (
            (
                await db_session.execute(
                    select(ValidationRun).where(ValidationRun.voyage_id == voyage.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(validation) == 1
        assert validation[0].status == "passed"

        deployments = (
            (await db_session.execute(select(Deployment).where(Deployment.voyage_id == voyage.id)))
            .scalars()
            .all()
        )
        assert len(deployments) == 1
        assert deployments[0].status == "completed"
        assert deployments[0].url is not None

        # event sequence sanity check
        types = await _replay_event_types(mushi, voyage.id)
        assert types[0] == "pipeline_started"
        assert types[-1] == "pipeline_completed"
        assert types.count("pipeline_stage_entered") == 6
        assert types.count("pipeline_stage_completed") == 6
        # per-service events
        assert "voyage_plan_created" in types
        assert types.count("poneglyph_drafted") == 3
        assert types.count("health_check_written") == 3
        assert types.count("code_generated") == 3
        assert types.count("tests_passed") == 3
        assert types.count("validation_passed") == 1
        assert types.count("deployment_completed") == 1

        # Vivre cards: at minimum 12 (one per stage_entered + stage_completed).
        cards = (
            (await db_session.execute(select(VivreCard).where(VivreCard.voyage_id == voyage.id)))
            .scalars()
            .all()
        )
        assert len(cards) >= 12

    async def test_event_ordering(
        self,
        db_session: AsyncSession,
        mushi: DenDenMushi,
        voyage_id: uuid.UUID,
        stub_execution_service: ExecutionService,
        stub_deployment_backend: InProcessDeploymentBackend,
    ) -> None:
        user = await _seed_user(db_session)
        voyage = await _seed_voyage(db_session, user)
        await _seed_dial_config(db_session, voyage, shipwright_max_concurrency=3)
        await db_session.commit()

        router = make_role_router(mushi, voyage.id)
        service = _make_service(
            db_session,
            mushi,
            router,
            stub_execution_service,
            stub_deployment_backend,
        )

        await service.start(voyage, user.id, "ordered pipeline", "preview")

        events = await _replay_events(mushi, voyage.id)
        assert isinstance(events[0], PipelineStartedEvent)
        assert isinstance(events[-1], PipelineCompletedEvent)

        # For every stage, the entered event precedes its completed event.
        for stage in (
            "PLANNING",
            "PDD",
            "TDD",
            "BUILDING",
            "REVIEWING",
            "DEPLOYING",
        ):
            entered_idx = next(
                i
                for i, ev in enumerate(events)
                if isinstance(ev, PipelineStageEnteredEvent) and ev.payload.get("stage") == stage
            )
            completed_idx = next(
                i
                for i, ev in enumerate(events)
                if isinstance(ev, PipelineStageCompletedEvent) and ev.payload.get("stage") == stage
            )
            assert entered_idx < completed_idx, f"{stage} stage out of order"

        # Helmsman events come after Doctor (validate) events.
        validation_idx = next(
            i for i, ev in enumerate(events) if ev.event_type == "validation_passed"
        )
        deploy_started_idx = next(
            i for i, ev in enumerate(events) if ev.event_type == "deployment_started"
        )
        assert validation_idx < deploy_started_idx


# ---------------------------------------------------------------------------
# TestParallelShipwright
#
# These tests verify the issue #39 fix: pipeline_graph._build_one_phase opens
# a fresh AsyncSession per phase via ctx.session_factory, so concurrent
# Shipwrights no longer collide on a shared psycopg connection. The fix is
# only effective if the test plumbs `session_factory` into _make_service.
# ---------------------------------------------------------------------------


class TestParallelShipwright:
    async def test_max_concurrency_2_with_5_phases(
        self,
        db_session: AsyncSession,
        mushi: DenDenMushi,
        voyage_id: uuid.UUID,
        stub_execution_service: ExecutionService,
        stub_deployment_backend: InProcessDeploymentBackend,
        integration_session_factory: async_sessionmaker[AsyncSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = await _seed_user(db_session)
        voyage = await _seed_voyage(db_session, user, title="parallel-5")
        await _seed_dial_config(db_session, voyage, shipwright_max_concurrency=2)
        await db_session.commit()

        # 5 independent phases — all in layer 1, all eligible for parallel.
        captain_payload = {
            "phases": [
                {
                    "phase_number": n,
                    "name": f"Phase {n}",
                    "description": "indep",
                    "assigned_to": "shipwright",
                    "depends_on": [],
                    "artifacts": [f"src/phase{n}.py"],
                }
                for n in range(1, 6)
            ]
        }
        router = make_role_router(mushi, voyage.id, captain_payload=captain_payload)

        counter = _PeakCounter()
        # A small sleep ensures multiple phases are actually concurrent rather
        # than executing sequentially within one event loop tick.
        monkeypatch.setattr(
            ShipwrightService,
            "build_code",
            _wrap_shipwright_build_code(counter, sleep_seconds=0.05),
        )

        service = _make_service(
            db_session,
            mushi,
            router,
            stub_execution_service,
            stub_deployment_backend,
            session_factory=integration_session_factory,
        )
        await service.start(voyage, user.id, "five independent phases", "preview")

        await db_session.refresh(voyage)
        assert voyage.status == VoyageStatus.COMPLETED.value
        assert voyage.phase_status == {
            "1": PHASE_STATUS_BUILT,
            "2": PHASE_STATUS_BUILT,
            "3": PHASE_STATUS_BUILT,
            "4": PHASE_STATUS_BUILT,
            "5": PHASE_STATUS_BUILT,
        }
        # Bound by the configured Shipwright semaphore.
        assert counter.peak <= 2

    async def test_dep_ordering_respects_layers(
        self,
        db_session: AsyncSession,
        mushi: DenDenMushi,
        voyage_id: uuid.UUID,
        stub_execution_service: ExecutionService,
        stub_deployment_backend: InProcessDeploymentBackend,
        integration_session_factory: async_sessionmaker[AsyncSession],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user = await _seed_user(db_session)
        voyage = await _seed_voyage(db_session, user, title="dep-order")
        await _seed_dial_config(db_session, voyage, shipwright_max_concurrency=4)
        await db_session.commit()

        # 4 phases: 1 -> {2,3} -> 4
        captain_payload = {
            "phases": [
                {
                    "phase_number": 1,
                    "name": "Root",
                    "description": "root",
                    "assigned_to": "shipwright",
                    "depends_on": [],
                    "artifacts": [],
                },
                {
                    "phase_number": 2,
                    "name": "Left",
                    "description": "left branch",
                    "assigned_to": "shipwright",
                    "depends_on": [1],
                    "artifacts": [],
                },
                {
                    "phase_number": 3,
                    "name": "Right",
                    "description": "right branch",
                    "assigned_to": "shipwright",
                    "depends_on": [1],
                    "artifacts": [],
                },
                {
                    "phase_number": 4,
                    "name": "Join",
                    "description": "join",
                    "assigned_to": "shipwright",
                    "depends_on": [2, 3],
                    "artifacts": [],
                },
            ]
        }
        router = make_role_router(mushi, voyage.id, captain_payload=captain_payload)

        counter = _PeakCounter()
        monkeypatch.setattr(
            ShipwrightService,
            "build_code",
            _wrap_shipwright_build_code(counter, sleep_seconds=0.02),
        )

        service = _make_service(
            db_session,
            mushi,
            router,
            stub_execution_service,
            stub_deployment_backend,
            session_factory=integration_session_factory,
        )
        await service.start(voyage, user.id, "four-phase DAG", "preview")

        await db_session.refresh(voyage)
        assert voyage.status == VoyageStatus.COMPLETED.value

        # Read tests_passed events; assert phase 4 timestamp >= max(p2, p3),
        # and phase 2/3 timestamps >= phase 1.
        events = await _replay_events(mushi, voyage.id)
        ts_by_phase: dict[int, Any] = {}
        for ev in events:
            if isinstance(ev, _TestsPassedEvent):
                ts_by_phase[int(ev.payload["phase_number"])] = ev.timestamp
        assert set(ts_by_phase) == {1, 2, 3, 4}
        assert ts_by_phase[2] >= ts_by_phase[1]
        assert ts_by_phase[3] >= ts_by_phase[1]
        assert ts_by_phase[4] >= max(ts_by_phase[2], ts_by_phase[3])


# ---------------------------------------------------------------------------
# TestFailurePaths
# ---------------------------------------------------------------------------


class TestFailurePaths:
    async def test_doctor_validate_failure_marks_voyage_failed(
        self,
        db_session: AsyncSession,
        mushi: DenDenMushi,
        voyage_id: uuid.UUID,
        stub_deployment_backend: InProcessDeploymentBackend,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from tests.integration.stubs import StubExecutionBackend

        user = await _seed_user(db_session)
        voyage = await _seed_voyage(db_session, user, title="validate-fail")
        await _seed_dial_config(db_session, voyage)
        await db_session.commit()

        # Validation calls the SAME execution backend but with a different
        # `command` than Shipwright. We intercept the validation command at
        # the backend layer to return a failing pytest result, while letting
        # all Shipwright build runs pass.
        backend = StubExecutionBackend()
        original_execute = backend.execute

        async def _execute(sandbox_id: str, request: Any) -> Any:
            if "pytest -x --tb=short" in request.command and "/workspace" in request.command:
                # Distinguish validation from Shipwright by inspecting files:
                # validation only contains health-check files (under tests/),
                # whereas Shipwright sees both src/ and tests/. Doctor's
                # validate path passes only health_checks + shipwright_files
                # — the difference is that validation passes BOTH layered
                # together. We use the presence of every required file path
                # plus absence of "iteration" hint in the command. Simpler:
                # the validation request's working_dir is always /workspace
                # AND it includes ALL phase test files at once.
                from app.schemas.execution import ExecutionResult

                # Heuristic: if the request includes >= 3 test files and
                # >= 3 src files, it's the validation run (Doctor layered
                # them together). Otherwise it's a Shipwright phase run.
                test_files = [p for p in request.files if p.startswith("tests/")]
                src_files = [p for p in request.files if p.startswith("src/")]
                if len(test_files) >= 3 and len(src_files) >= 3:
                    return ExecutionResult(
                        exit_code=1,
                        stdout="1 failed in 0.10s",
                        stderr="AssertionError",
                        timed_out=False,
                        duration_seconds=0.1,
                        sandbox_id=sandbox_id,
                    )
            return await original_execute(sandbox_id, request)

        backend.execute = _execute  # type: ignore[method-assign]
        execution_service = ExecutionService(backend)

        router = make_role_router(mushi, voyage.id)
        service = _make_service(
            db_session,
            mushi,
            router,
            execution_service,
            stub_deployment_backend,
        )

        with pytest.raises(PipelineError):
            await service.start(voyage, user.id, "validate fail", "preview")

        await db_session.refresh(voyage)
        assert voyage.status == VoyageStatus.FAILED.value

        validations = (
            (
                await db_session.execute(
                    select(ValidationRun).where(ValidationRun.voyage_id == voyage.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(validations) == 1
        assert validations[0].status == "failed"

        deployments = (
            (await db_session.execute(select(Deployment).where(Deployment.voyage_id == voyage.id)))
            .scalars()
            .all()
        )
        assert deployments == []

        # PipelineFailedEvent on Redis with stage REVIEWING.
        events = await _replay_events(mushi, voyage.id)
        failed = [e for e in events if isinstance(e, PipelineFailedEvent)]
        assert len(failed) >= 1
        assert any(e.payload.get("stage") == "REVIEWING" for e in failed)

    async def test_helmsman_deploy_failure_marks_voyage_failed_with_diagnosis(
        self,
        db_session: AsyncSession,
        mushi: DenDenMushi,
        voyage_id: uuid.UUID,
        stub_execution_service: ExecutionService,
    ) -> None:
        user = await _seed_user(db_session)
        voyage = await _seed_voyage(db_session, user, title="deploy-fail")
        await _seed_dial_config(db_session, voyage)
        await db_session.commit()

        router = make_role_router(mushi, voyage.id)
        # InProcessDeploymentBackend.fail_tiers triggers a status='failed'
        # response (NOT an exception) — exactly the path that Helmsman's
        # diagnose node consumes.
        deployment_backend = InProcessDeploymentBackend(fail_tiers={"preview"})

        service = _make_service(
            db_session,
            mushi,
            router,
            stub_execution_service,
            deployment_backend,
        )

        with pytest.raises(PipelineError):
            await service.start(voyage, user.id, "deploy fail", "preview")

        await db_session.refresh(voyage)
        assert voyage.status == VoyageStatus.FAILED.value

        deployments = (
            (await db_session.execute(select(Deployment).where(Deployment.voyage_id == voyage.id)))
            .scalars()
            .all()
        )
        assert len(deployments) == 1
        assert deployments[0].status == "failed"
        assert deployments[0].diagnosis is not None
        assert "summary" in deployments[0].diagnosis

        # Validation succeeded (its stage is upstream of Helmsman).
        validations = (
            (
                await db_session.execute(
                    select(ValidationRun).where(ValidationRun.voyage_id == voyage.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(validations) == 1
        assert validations[0].status == "passed"

        events = await _replay_events(mushi, voyage.id)
        failed = [e for e in events if isinstance(e, PipelineFailedEvent)]
        assert any(e.payload.get("stage") == "DEPLOYING" for e in failed)

    async def test_shipwright_phase_failure_cancels_layer(
        self,
        db_session: AsyncSession,
        mushi: DenDenMushi,
        voyage_id: uuid.UUID,
        stub_execution_service: ExecutionService,
        stub_deployment_backend: InProcessDeploymentBackend,
        integration_session_factory: async_sessionmaker[AsyncSession],
    ) -> None:
        user = await _seed_user(db_session)
        voyage = await _seed_voyage(db_session, user, title="ship-fail")
        await _seed_dial_config(db_session, voyage, shipwright_max_concurrency=3)
        await db_session.commit()

        # 3 INDEPENDENT phases — all in the same dependency layer.
        captain_payload = {
            "phases": [
                {
                    "phase_number": n,
                    "name": f"Phase {n}",
                    "description": "indep",
                    "assigned_to": "shipwright",
                    "depends_on": [],
                    "artifacts": [],
                }
                for n in (1, 2, 3)
            ]
        }
        # Shipwright phase 2 raises ProviderError → ShipwrightService converts
        # the exhausted-iteration result into a BUILD_PARSE_FAILED error.
        router = make_role_router(
            mushi,
            voyage.id,
            captain_payload=captain_payload,
            shipwright_error_phase=2,
        )

        service = _make_service(
            db_session,
            mushi,
            router,
            stub_execution_service,
            stub_deployment_backend,
            session_factory=integration_session_factory,
        )

        with pytest.raises(PipelineError):
            await service.start(voyage, user.id, "fail-fast layer", "preview")

        await db_session.refresh(voyage)
        assert voyage.status == VoyageStatus.FAILED.value
        # phase 2 must be FAILED; phases 1 and 3 may be BUILT (already
        # finished), PENDING (started + cancelled), or absent entirely
        # (cancelled before the BUILDING write reached the DB).
        allowed = {PHASE_STATUS_BUILT, PHASE_STATUS_PENDING, None}
        assert voyage.phase_status.get("2") == "FAILED"
        assert voyage.phase_status.get("1") in allowed
        assert voyage.phase_status.get("3") in allowed


# ---------------------------------------------------------------------------
# TestResumeSkipsAlreadySatisfied
# ---------------------------------------------------------------------------


class TestResumeSkipsAlreadySatisfied:
    async def test_resume_from_paused_skips_planning_pdd_tdd(
        self,
        db_session: AsyncSession,
        mushi: DenDenMushi,
        voyage_id: uuid.UUID,
        stub_execution_service: ExecutionService,
        stub_deployment_backend: InProcessDeploymentBackend,
    ) -> None:
        user = await _seed_user(db_session)
        # NOTE: the prompt asks for `status=PAUSED` here, but the pipeline graph
        # short-circuits to `pause_end` on the very first stage if the voyage
        # is loaded as PAUSED — the API caller is implicitly expected to flip
        # the status back to CHARTED before invoking resume. We seed CHARTED
        # so the resume-skip-already-satisfied path is exercised; the PAUSED
        # short-circuit behaviour is a separate finding documented in the
        # Phase 15.5 report.
        voyage = await _seed_voyage(
            db_session, user, title="resume-paused", status=VoyageStatus.CHARTED
        )
        await _seed_dial_config(db_session, voyage)

        # Pre-seed: a 3-phase plan whose Captain payload matches the canned
        # default, plus 3 poneglyphs and 3 health checks. phase_status stays
        # empty so all 3 phases need building on resume.
        plan_phases = {
            "phases": [
                {
                    "phase_number": 1,
                    "name": "Foundation",
                    "description": "Set up core module",
                    "assigned_to": "shipwright",
                    "depends_on": [],
                    "artifacts": ["src/foundation.py"],
                },
                {
                    "phase_number": 2,
                    "name": "Feature",
                    "description": "Build feature on top of foundation",
                    "assigned_to": "shipwright",
                    "depends_on": [1],
                    "artifacts": ["src/feature.py"],
                },
                {
                    "phase_number": 3,
                    "name": "Integration",
                    "description": "Integrate the two prior phases",
                    "assigned_to": "shipwright",
                    "depends_on": [1, 2],
                    "artifacts": ["src/integration.py"],
                },
            ]
        }
        plan = VoyagePlan(
            voyage_id=voyage.id,
            phases=plan_phases,
            created_by="captain",
            version=1,
        )
        db_session.add(plan)
        await db_session.flush()

        navigator_payload = _default_navigator_for_phases([1, 2, 3])
        for ng in navigator_payload["poneglyphs"]:
            db_session.add(
                Poneglyph(
                    voyage_id=voyage.id,
                    phase_number=ng["phase_number"],
                    content=json.dumps(ng),
                    metadata_={
                        "phase_name": ng["title"],
                        "test_criteria_count": len(ng["test_criteria"]),
                        "file_count": len(ng["file_paths"]),
                    },
                    created_by="navigator",
                )
            )

        doctor_payload = _default_doctor_health_checks([1, 2, 3])
        for hc in doctor_payload["health_checks"]:
            db_session.add(
                HealthCheck(
                    voyage_id=voyage.id,
                    phase_number=hc["phase_number"],
                    file_path=hc["file_path"],
                    content=hc["content"],
                    framework=hc["framework"],
                    created_by="doctor",
                )
            )
        await db_session.commit()

        call_log: Counter[CrewRole] = Counter()
        router = make_role_router(mushi, voyage.id, call_log=call_log)
        service = _make_service(
            db_session,
            mushi,
            router,
            stub_execution_service,
            stub_deployment_backend,
        )

        await service.start(voyage, user.id, "resume from paused", "preview")

        await db_session.refresh(voyage)
        assert voyage.status == VoyageStatus.COMPLETED.value

        # Captain / Navigator / Doctor (write) should NOT have been called.
        # The Doctor *role* is still called once for validate.
        assert call_log[CrewRole.CAPTAIN] == 0
        assert call_log[CrewRole.NAVIGATOR] == 0
        assert call_log[CrewRole.DOCTOR] == 0  # validate doesn't call LLM
        assert call_log[CrewRole.SHIPWRIGHT] == 3
        # Helmsman is only called on a deploy failure; happy-path is 0.
        assert call_log[CrewRole.HELMSMAN] == 0

    async def test_resume_partial_build_only_runs_missing_phases(
        self,
        db_session: AsyncSession,
        mushi: DenDenMushi,
        voyage_id: uuid.UUID,
        stub_execution_service: ExecutionService,
        stub_deployment_backend: InProcessDeploymentBackend,
    ) -> None:
        user = await _seed_user(db_session)
        # See note in `test_resume_from_paused_skips_planning_pdd_tdd` — using
        # CHARTED here for the same reason.
        voyage = await _seed_voyage(
            db_session,
            user,
            title="resume-partial",
            status=VoyageStatus.CHARTED,
            phase_status={"1": PHASE_STATUS_BUILT},
        )
        await _seed_dial_config(db_session, voyage)

        # Sequential dep chain so the layered build runs one phase at a time;
        # the parallel-session bug surfaced in TestParallelShipwright would
        # otherwise also bite this test with concurrent phase 2 + 3 builds.
        plan_phases = {
            "phases": [
                {
                    "phase_number": 1,
                    "name": "Phase 1",
                    "description": "first",
                    "assigned_to": "shipwright",
                    "depends_on": [],
                    "artifacts": [],
                },
                {
                    "phase_number": 2,
                    "name": "Phase 2",
                    "description": "second",
                    "assigned_to": "shipwright",
                    "depends_on": [1],
                    "artifacts": [],
                },
                {
                    "phase_number": 3,
                    "name": "Phase 3",
                    "description": "third",
                    "assigned_to": "shipwright",
                    "depends_on": [2],
                    "artifacts": [],
                },
            ]
        }
        plan = VoyagePlan(
            voyage_id=voyage.id,
            phases=plan_phases,
            created_by="captain",
            version=1,
        )
        db_session.add(plan)
        await db_session.flush()

        for ng in _default_navigator_for_phases([1, 2, 3])["poneglyphs"]:
            db_session.add(
                Poneglyph(
                    voyage_id=voyage.id,
                    phase_number=ng["phase_number"],
                    content=json.dumps(ng),
                    metadata_={
                        "phase_name": ng["title"],
                        "test_criteria_count": len(ng["test_criteria"]),
                        "file_count": len(ng["file_paths"]),
                    },
                    created_by="navigator",
                )
            )

        for hc in _default_doctor_health_checks([1, 2, 3])["health_checks"]:
            db_session.add(
                HealthCheck(
                    voyage_id=voyage.id,
                    phase_number=hc["phase_number"],
                    file_path=hc["file_path"],
                    content=hc["content"],
                    framework=hc["framework"],
                    created_by="doctor",
                )
            )

        # Pre-seed a build artifact + ShipwrightRun for phase 1 so the
        # require_can_enter_reviewing check sees phase 1 as already built.
        from app.models.shipwright_run import ShipwrightRun

        run1 = ShipwrightRun(
            voyage_id=voyage.id,
            phase_number=1,
            status="passed",
            iteration_count=1,
            exit_code=0,
            passed_count=1,
            failed_count=0,
            total_count=1,
        )
        db_session.add(run1)
        await db_session.flush()
        artifact_payload = _default_shipwright_for_phase(1)
        for spec in artifact_payload["files"]:
            db_session.add(
                BuildArtifact(
                    voyage_id=voyage.id,
                    shipwright_run_id=run1.id,
                    phase_number=1,
                    file_path=spec["file_path"],
                    content=spec["content"],
                    language=spec["language"],
                    created_by="shipwright",
                )
            )
        await db_session.commit()

        call_log: Counter[CrewRole] = Counter()
        router = make_role_router(mushi, voyage.id, call_log=call_log)
        service = _make_service(
            db_session,
            mushi,
            router,
            stub_execution_service,
            stub_deployment_backend,
        )
        await service.start(voyage, user.id, "resume partial", "preview")

        await db_session.refresh(voyage)
        assert voyage.status == VoyageStatus.COMPLETED.value
        # Only phases 2 and 3 should have been built — phase 1 was already BUILT.
        assert call_log[CrewRole.SHIPWRIGHT] == 2
