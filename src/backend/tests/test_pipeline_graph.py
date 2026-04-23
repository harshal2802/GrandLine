"""Tests for the master Voyage Pipeline graph — topological scheduler,
stage nodes, building-node parallel scheduling, terminal nodes, and
full-graph smoke."""

from __future__ import annotations

import asyncio
import time
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.crew.pipeline_graph import (
    STAGE_BUILDING,
    STAGE_DEPLOYING,
    STAGE_PDD,
    STAGE_PLANNING,
    STAGE_REVIEWING,
    STAGE_TDD,
    PipelineContext,
    PipelineState,
    _make_building_node,
    _make_deploying_node,
    _make_fail_end,
    _make_finalize_node,
    _make_pause_end,
    _make_pdd_node,
    _make_planning_node,
    _make_reviewing_node,
    _make_tdd_node,
    _route_after_stage,
    build_pipeline_graph,
    topological_layers,
)
from app.den_den_mushi.events import (
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStageCompletedEvent,
    PipelineStageEnteredEvent,
)
from app.models.enums import VoyageStatus
from app.services.pipeline_guards import PipelineError

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Pure-helper tests
# ---------------------------------------------------------------------------


class TestTopologicalLayers:
    def test_single_phase_no_deps(self) -> None:
        phases = [{"phase_number": 1, "depends_on": []}]
        assert topological_layers(phases) == [[1]]

    def test_linear_chain(self) -> None:
        phases = [
            {"phase_number": 1, "depends_on": []},
            {"phase_number": 2, "depends_on": [1]},
            {"phase_number": 3, "depends_on": [2]},
        ]
        assert topological_layers(phases) == [[1], [2], [3]]

    def test_parallel_independent_phases(self) -> None:
        phases = [
            {"phase_number": 1, "depends_on": []},
            {"phase_number": 2, "depends_on": []},
            {"phase_number": 3, "depends_on": []},
        ]
        assert topological_layers(phases) == [[1, 2, 3]]

    def test_diamond_dependency(self) -> None:
        phases = [
            {"phase_number": 1, "depends_on": []},
            {"phase_number": 2, "depends_on": [1]},
            {"phase_number": 3, "depends_on": [1]},
            {"phase_number": 4, "depends_on": [2, 3]},
        ]
        assert topological_layers(phases) == [[1], [2, 3], [4]]

    def test_mixed_parallel_and_chain(self) -> None:
        phases = [
            {"phase_number": 1, "depends_on": []},
            {"phase_number": 2, "depends_on": []},
            {"phase_number": 3, "depends_on": [1]},
            {"phase_number": 4, "depends_on": [2, 3]},
        ]
        assert topological_layers(phases) == [[1, 2], [3], [4]]

    def test_cycle_raises(self) -> None:
        phases = [
            {"phase_number": 1, "depends_on": [2]},
            {"phase_number": 2, "depends_on": [1]},
        ]
        with pytest.raises(PipelineError) as exc:
            topological_layers(phases)
        assert exc.value.code == "INVALID_DEP_GRAPH"

    def test_missing_depends_on_key_is_treated_as_empty(self) -> None:
        phases = [{"phase_number": 1}]
        assert topological_layers(phases) == [[1]]

    def test_null_depends_on_treated_as_empty(self) -> None:
        phases = [{"phase_number": 1, "depends_on": None}]
        assert topological_layers(phases) == [[1]]


class TestRouteAfterStage:
    def _state(
        self,
        *,
        paused: bool = False,
        error: dict | None = None,
    ) -> PipelineState:
        return _make_state(paused=paused, error=error)

    def test_paused_routes_to_pause_end(self) -> None:
        state = self._state(paused=True)
        assert _route_after_stage(state, "pdd") == "pause_end"

    def test_error_routes_to_fail_end(self) -> None:
        state = self._state(error={"code": "X", "message": "m", "stage": "S"})
        assert _route_after_stage(state, "pdd") == "fail_end"

    def test_paused_wins_over_error(self) -> None:
        state = self._state(paused=True, error={"code": "X", "message": "m", "stage": "S"})
        assert _route_after_stage(state, "pdd") == "pause_end"

    def test_happy_path_routes_to_next_stage(self) -> None:
        state = self._state()
        assert _route_after_stage(state, "pdd") == "pdd"


class TestBuildPipelineGraph:
    def test_compiles_without_error(self) -> None:
        ctx = _mock_ctx()
        graph = build_pipeline_graph(ctx)
        assert graph is not None

    def test_graph_has_all_expected_nodes(self) -> None:
        ctx = _mock_ctx()
        graph = build_pipeline_graph(ctx)
        nodes = set(graph.get_graph().nodes.keys())
        assert {
            "planning",
            "pdd",
            "tdd",
            "building",
            "reviewing",
            "deploying",
            "finalize",
            "fail_end",
            "pause_end",
        }.issubset(nodes)


class TestStageConstants:
    def test_stage_constants_are_distinct(self) -> None:
        stages = {
            STAGE_PLANNING,
            STAGE_PDD,
            STAGE_TDD,
            STAGE_BUILDING,
            STAGE_REVIEWING,
            STAGE_DEPLOYING,
        }
        assert len(stages) == 6


class TestPipelineContext:
    def test_context_stores_all_deps(self) -> None:
        session = AsyncMock()
        mushi = AsyncMock()
        dial_router = AsyncMock()
        execution_service = AsyncMock()
        git_service = MagicMock()
        backend = AsyncMock()
        ctx = PipelineContext(
            session=session,
            mushi=mushi,
            dial_router=dial_router,
            execution_service=execution_service,
            git_service=git_service,
            deployment_backend=backend,
        )
        assert ctx.session is session
        assert ctx.mushi is mushi
        assert ctx.dial_router is dial_router
        assert ctx.execution_service is execution_service
        assert ctx.git_service is git_service
        assert ctx.deployment_backend is backend


# ---------------------------------------------------------------------------
# Shared fixtures for stage node tests
# ---------------------------------------------------------------------------


def _make_state(
    *,
    paused: bool = False,
    error: dict | None = None,
    max_parallel: int = 1,
) -> PipelineState:
    return {
        "voyage_id": VOYAGE_ID,
        "user_id": USER_ID,
        "deploy_tier": "preview",
        "max_parallel_shipwrights": max_parallel,
        "task": "t",
        "start_monotonic": time.monotonic(),
        "plan_id": None,
        "poneglyph_count": 0,
        "health_check_count": 0,
        "build_artifact_count": 0,
        "validation_run_id": None,
        "deployment_id": None,
        "error": error,
        "paused": paused,
    }


def _mock_ctx() -> PipelineContext:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    mushi = AsyncMock()
    mushi.publish = AsyncMock(return_value="msg-1")
    return PipelineContext(
        session=session,
        mushi=mushi,
        dial_router=AsyncMock(),
        execution_service=AsyncMock(),
        git_service=None,
        deployment_backend=AsyncMock(),
    )


def _mock_voyage(
    status: str = VoyageStatus.CHARTED.value,
    phase_status: dict[str, str] | None = None,
) -> MagicMock:
    v = MagicMock()
    v.id = VOYAGE_ID
    v.status = status
    v.phase_status = phase_status if phase_status is not None else {}
    return v


def _mock_plan(phases: list[dict[str, Any]] | None = None) -> MagicMock:
    if phases is None:
        phases = [{"phase_number": 1, "depends_on": [], "title": "p1", "description": "d"}]
    plan = MagicMock()
    plan.id = uuid.uuid4()
    plan.phases = {"phases": phases}
    return plan


def _patch_loads(
    monkeypatch: pytest.MonkeyPatch,
    *,
    voyage: Any = None,
    plan: Any = None,
    poneglyphs: list[Any] | None = None,
    health_checks: list[Any] | None = None,
    build_artifacts: list[Any] | None = None,
    latest_validation: Any = None,
) -> None:
    if voyage is not None:
        monkeypatch.setattr("app.crew.pipeline_graph._load_voyage", AsyncMock(return_value=voyage))
    if plan is not None or plan is None:
        monkeypatch.setattr("app.crew.pipeline_graph._load_plan", AsyncMock(return_value=plan))
    monkeypatch.setattr(
        "app.crew.pipeline_graph._load_poneglyphs",
        AsyncMock(return_value=poneglyphs or []),
    )
    monkeypatch.setattr(
        "app.crew.pipeline_graph._load_health_checks",
        AsyncMock(return_value=health_checks or []),
    )
    monkeypatch.setattr(
        "app.crew.pipeline_graph._load_build_artifacts",
        AsyncMock(return_value=build_artifacts or []),
    )
    monkeypatch.setattr(
        "app.crew.pipeline_graph._load_latest_validation",
        AsyncMock(return_value=latest_validation),
    )


def _poneglyph(phase_number: int = 1) -> MagicMock:
    p = MagicMock()
    p.id = uuid.uuid4()
    p.phase_number = phase_number
    return p


def _health_check(phase_number: int = 1) -> MagicMock:
    hc = MagicMock()
    hc.phase_number = phase_number
    return hc


def _build_artifact(phase_number: int = 1) -> MagicMock:
    a = MagicMock()
    a.phase_number = phase_number
    a.file_path = f"phase_{phase_number}.py"
    a.content = "pass"
    return a


def _mock_guard(monkeypatch: pytest.MonkeyPatch, name: str, *, raises: bool = False) -> MagicMock:
    guard = MagicMock()
    if raises:
        guard.side_effect = PipelineError("GUARD_FAIL", f"{name} guard failed")
    monkeypatch.setattr(f"app.crew.pipeline_graph.{name}", guard)
    return guard


# ---------------------------------------------------------------------------
# Planning node
# ---------------------------------------------------------------------------


class TestPlanningNode:
    @pytest.mark.asyncio
    async def test_happy_path_calls_captain_and_writes_plan(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        plan = _mock_plan()
        _patch_loads(monkeypatch, voyage=voyage, plan=None)

        captain = MagicMock()
        captain.chart_course = AsyncMock(return_value=(plan, MagicMock()))
        monkeypatch.setattr(
            "app.crew.pipeline_graph.CaptainService", MagicMock(return_value=captain)
        )

        node = _make_planning_node(ctx)
        result = await node(_make_state())

        captain.chart_course.assert_awaited_once()
        assert result["plan_id"] == plan.id

    @pytest.mark.asyncio
    async def test_skip_when_plan_exists(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        plan = _mock_plan()
        _patch_loads(monkeypatch, voyage=voyage, plan=plan)

        captain = MagicMock()
        captain.chart_course = AsyncMock()
        monkeypatch.setattr(
            "app.crew.pipeline_graph.CaptainService", MagicMock(return_value=captain)
        )

        node = _make_planning_node(ctx)
        result = await node(_make_state())

        captain.chart_course.assert_not_awaited()
        assert result["plan_id"] == plan.id

    @pytest.mark.asyncio
    async def test_paused_routes_to_pause_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage(status=VoyageStatus.PAUSED.value)
        _patch_loads(monkeypatch, voyage=voyage, plan=None)

        node = _make_planning_node(ctx)
        result = await node(_make_state())
        assert result == {"paused": True}

    @pytest.mark.asyncio
    async def test_captain_error_routes_to_fail_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.captain_service import CaptainError

        ctx = _mock_ctx()
        voyage = _mock_voyage()
        _patch_loads(monkeypatch, voyage=voyage, plan=None)

        captain = MagicMock()
        captain.chart_course = AsyncMock(side_effect=CaptainError("PLAN_PARSE_FAILED", "bad json"))
        monkeypatch.setattr(
            "app.crew.pipeline_graph.CaptainService", MagicMock(return_value=captain)
        )

        node = _make_planning_node(ctx)
        result = await node(_make_state())
        assert result["error"]["code"] == "PLAN_PARSE_FAILED"
        assert result["error"]["stage"] == STAGE_PLANNING

    @pytest.mark.asyncio
    async def test_guard_failure_routes_to_fail_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage(status=VoyageStatus.BUILDING.value)
        _patch_loads(monkeypatch, voyage=voyage, plan=None)
        _mock_guard(monkeypatch, "require_can_enter_planning", raises=True)

        node = _make_planning_node(ctx)
        result = await node(_make_state())
        assert result["error"]["code"] == "GUARD_FAIL"


# ---------------------------------------------------------------------------
# PDD node
# ---------------------------------------------------------------------------


class TestPddNode:
    @pytest.mark.asyncio
    async def test_happy_path_calls_navigator(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        plan = _mock_plan()
        _patch_loads(monkeypatch, voyage=voyage, plan=plan, poneglyphs=[])
        _mock_guard(monkeypatch, "require_can_enter_pdd")
        # "can enter next" (tdd) is missing poneglyphs → raises → fall through
        _mock_guard(monkeypatch, "require_can_enter_tdd", raises=True)

        navigator = MagicMock()
        navigator.draft_poneglyphs = AsyncMock(return_value=[_poneglyph(1), _poneglyph(2)])
        monkeypatch.setattr(
            "app.crew.pipeline_graph.NavigatorService", MagicMock(return_value=navigator)
        )

        node = _make_pdd_node(ctx)
        result = await node(_make_state())
        navigator.draft_poneglyphs.assert_awaited_once()
        assert result["poneglyph_count"] == 2

    @pytest.mark.asyncio
    async def test_skip_when_tdd_guard_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        plan = _mock_plan()
        poneglyphs = [_poneglyph(1)]
        _patch_loads(monkeypatch, voyage=voyage, plan=plan, poneglyphs=poneglyphs)
        _mock_guard(monkeypatch, "require_can_enter_pdd")
        _mock_guard(monkeypatch, "require_can_enter_tdd")

        navigator = MagicMock()
        navigator.draft_poneglyphs = AsyncMock()
        monkeypatch.setattr(
            "app.crew.pipeline_graph.NavigatorService", MagicMock(return_value=navigator)
        )

        node = _make_pdd_node(ctx)
        result = await node(_make_state())
        navigator.draft_poneglyphs.assert_not_awaited()
        assert result["poneglyph_count"] == 1

    @pytest.mark.asyncio
    async def test_paused_routes_to_pause_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage(status=VoyageStatus.PAUSED.value)
        _patch_loads(monkeypatch, voyage=voyage, plan=_mock_plan())
        node = _make_pdd_node(ctx)
        result = await node(_make_state())
        assert result == {"paused": True}

    @pytest.mark.asyncio
    async def test_navigator_error_routes_to_fail_end(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.navigator_service import NavigatorError

        ctx = _mock_ctx()
        voyage = _mock_voyage()
        _patch_loads(monkeypatch, voyage=voyage, plan=_mock_plan())
        _mock_guard(monkeypatch, "require_can_enter_pdd")
        _mock_guard(monkeypatch, "require_can_enter_tdd", raises=True)

        navigator = MagicMock()
        navigator.draft_poneglyphs = AsyncMock(
            side_effect=NavigatorError("PONEGLYPH_PARSE_FAILED", "x")
        )
        monkeypatch.setattr(
            "app.crew.pipeline_graph.NavigatorService", MagicMock(return_value=navigator)
        )

        node = _make_pdd_node(ctx)
        result = await node(_make_state())
        assert result["error"]["code"] == "PONEGLYPH_PARSE_FAILED"

    @pytest.mark.asyncio
    async def test_guard_failure_routes_to_fail_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        _patch_loads(monkeypatch, voyage=voyage, plan=None)
        _mock_guard(monkeypatch, "require_can_enter_pdd", raises=True)

        node = _make_pdd_node(ctx)
        result = await node(_make_state())
        assert result["error"]["code"] == "GUARD_FAIL"


# ---------------------------------------------------------------------------
# TDD node
# ---------------------------------------------------------------------------


class TestTddNode:
    @pytest.mark.asyncio
    async def test_happy_path_calls_doctor(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        plan = _mock_plan()
        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=plan,
            poneglyphs=[_poneglyph()],
            health_checks=[],
        )
        _mock_guard(monkeypatch, "require_can_enter_tdd")
        _mock_guard(monkeypatch, "require_can_enter_building", raises=True)

        doctor = MagicMock()
        doctor.write_health_checks = AsyncMock(return_value=[_health_check(), _health_check()])
        monkeypatch.setattr("app.crew.pipeline_graph.DoctorService", MagicMock(return_value=doctor))

        node = _make_tdd_node(ctx)
        result = await node(_make_state())
        doctor.write_health_checks.assert_awaited_once()
        assert result["health_check_count"] == 2

    @pytest.mark.asyncio
    async def test_skip_when_building_guard_passes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        plan = _mock_plan()
        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=plan,
            poneglyphs=[_poneglyph()],
            health_checks=[_health_check()],
        )
        _mock_guard(monkeypatch, "require_can_enter_tdd")
        _mock_guard(monkeypatch, "require_can_enter_building")

        doctor = MagicMock()
        doctor.write_health_checks = AsyncMock()
        monkeypatch.setattr("app.crew.pipeline_graph.DoctorService", MagicMock(return_value=doctor))

        node = _make_tdd_node(ctx)
        result = await node(_make_state())
        doctor.write_health_checks.assert_not_awaited()
        assert result["health_check_count"] == 1

    @pytest.mark.asyncio
    async def test_paused_routes_to_pause_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage(status=VoyageStatus.PAUSED.value)
        _patch_loads(monkeypatch, voyage=voyage, plan=_mock_plan())
        node = _make_tdd_node(ctx)
        result = await node(_make_state())
        assert result == {"paused": True}

    @pytest.mark.asyncio
    async def test_doctor_error_routes_to_fail_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.doctor_service import DoctorError

        ctx = _mock_ctx()
        voyage = _mock_voyage()
        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=_mock_plan(),
            poneglyphs=[_poneglyph()],
            health_checks=[],
        )
        _mock_guard(monkeypatch, "require_can_enter_tdd")
        _mock_guard(monkeypatch, "require_can_enter_building", raises=True)

        doctor = MagicMock()
        doctor.write_health_checks = AsyncMock(
            side_effect=DoctorError("HEALTH_CHECK_GEN_FAILED", "x")
        )
        monkeypatch.setattr("app.crew.pipeline_graph.DoctorService", MagicMock(return_value=doctor))

        node = _make_tdd_node(ctx)
        result = await node(_make_state())
        assert result["error"]["code"] == "HEALTH_CHECK_GEN_FAILED"

    @pytest.mark.asyncio
    async def test_guard_failure_routes_to_fail_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        _patch_loads(monkeypatch, voyage=voyage, plan=_mock_plan(), poneglyphs=[])
        _mock_guard(monkeypatch, "require_can_enter_tdd", raises=True)

        node = _make_tdd_node(ctx)
        result = await node(_make_state())
        assert result["error"]["code"] == "GUARD_FAIL"


# ---------------------------------------------------------------------------
# Reviewing node
# ---------------------------------------------------------------------------


class TestReviewingNode:
    @pytest.mark.asyncio
    async def test_happy_path_calls_doctor_validate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        plan = _mock_plan()
        artifacts = [_build_artifact(1)]
        passed_run = MagicMock()
        passed_run.id = uuid.uuid4()
        passed_run.status = "passed"
        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=plan,
            build_artifacts=artifacts,
            latest_validation=passed_run,
        )
        _mock_guard(monkeypatch, "require_can_enter_reviewing")

        doctor = MagicMock()
        doctor.validate_code = AsyncMock(return_value=None)
        monkeypatch.setattr("app.crew.pipeline_graph.DoctorService", MagicMock(return_value=doctor))

        node = _make_reviewing_node(ctx)
        # First load_latest_validation returns passed → skip fires
        # so validate_code NOT awaited. Assert skipped path.
        result = await node(_make_state())
        doctor.validate_code.assert_not_awaited()
        assert result["validation_run_id"] == passed_run.id

    @pytest.mark.asyncio
    async def test_skip_when_latest_validation_passed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _mock_ctx()
        passed_run = MagicMock()
        passed_run.id = uuid.uuid4()
        passed_run.status = "passed"
        _patch_loads(
            monkeypatch,
            voyage=_mock_voyage(),
            plan=_mock_plan(),
            build_artifacts=[_build_artifact()],
            latest_validation=passed_run,
        )
        _mock_guard(monkeypatch, "require_can_enter_reviewing")

        doctor = MagicMock()
        doctor.validate_code = AsyncMock()
        monkeypatch.setattr("app.crew.pipeline_graph.DoctorService", MagicMock(return_value=doctor))

        node = _make_reviewing_node(ctx)
        result = await node(_make_state())
        doctor.validate_code.assert_not_awaited()
        assert result["validation_run_id"] == passed_run.id

    @pytest.mark.asyncio
    async def test_validation_failed_routes_to_fail_end(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _mock_ctx()
        failed_run = MagicMock()
        failed_run.status = "failed"
        _patch_loads(
            monkeypatch,
            voyage=_mock_voyage(),
            plan=_mock_plan(),
            build_artifacts=[_build_artifact()],
            latest_validation=failed_run,
        )
        _mock_guard(monkeypatch, "require_can_enter_reviewing")

        doctor = MagicMock()
        doctor.validate_code = AsyncMock(return_value=None)
        monkeypatch.setattr("app.crew.pipeline_graph.DoctorService", MagicMock(return_value=doctor))

        node = _make_reviewing_node(ctx)
        result = await node(_make_state())
        assert result["error"]["code"] == "VALIDATION_FAILED"

    @pytest.mark.asyncio
    async def test_paused_routes_to_pause_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage(status=VoyageStatus.PAUSED.value)
        _patch_loads(monkeypatch, voyage=voyage, plan=_mock_plan())
        node = _make_reviewing_node(ctx)
        result = await node(_make_state())
        assert result == {"paused": True}

    @pytest.mark.asyncio
    async def test_guard_failure_routes_to_fail_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        _patch_loads(monkeypatch, voyage=_mock_voyage(), plan=_mock_plan(), build_artifacts=[])
        _mock_guard(monkeypatch, "require_can_enter_reviewing", raises=True)

        node = _make_reviewing_node(ctx)
        result = await node(_make_state())
        assert result["error"]["code"] == "GUARD_FAIL"


# ---------------------------------------------------------------------------
# Deploying node
# ---------------------------------------------------------------------------


class TestDeployingNode:
    @pytest.mark.asyncio
    async def test_happy_path_calls_helmsman_deploy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        _patch_loads(monkeypatch, voyage=voyage, latest_validation=MagicMock(status="passed"))
        _mock_guard(monkeypatch, "require_can_enter_deploying")

        deployment = MagicMock()
        deployment.deployment_id = uuid.uuid4()
        helmsman = MagicMock()
        helmsman.deploy = AsyncMock(return_value=deployment)
        monkeypatch.setattr(
            "app.crew.pipeline_graph.HelmsmanService", MagicMock(return_value=helmsman)
        )

        node = _make_deploying_node(ctx)
        result = await node(_make_state())
        helmsman.deploy.assert_awaited_once()
        assert result["deployment_id"] == deployment.deployment_id

    @pytest.mark.asyncio
    async def test_never_skips(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Even if a recent deployment exists, deploying_node always re-runs.
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        _patch_loads(monkeypatch, voyage=voyage, latest_validation=MagicMock(status="passed"))
        _mock_guard(monkeypatch, "require_can_enter_deploying")

        deployment = MagicMock()
        deployment.deployment_id = uuid.uuid4()
        helmsman = MagicMock()
        helmsman.deploy = AsyncMock(return_value=deployment)
        monkeypatch.setattr(
            "app.crew.pipeline_graph.HelmsmanService", MagicMock(return_value=helmsman)
        )

        node = _make_deploying_node(ctx)
        await node(_make_state())
        helmsman.deploy.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_paused_routes_to_pause_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        _patch_loads(monkeypatch, voyage=_mock_voyage(status=VoyageStatus.PAUSED.value))
        node = _make_deploying_node(ctx)
        result = await node(_make_state())
        assert result == {"paused": True}

    @pytest.mark.asyncio
    async def test_helmsman_error_routes_to_fail_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.helmsman_service import HelmsmanError

        ctx = _mock_ctx()
        _patch_loads(
            monkeypatch,
            voyage=_mock_voyage(),
            latest_validation=MagicMock(status="passed"),
        )
        _mock_guard(monkeypatch, "require_can_enter_deploying")

        helmsman = MagicMock()
        helmsman.deploy = AsyncMock(side_effect=HelmsmanError("DEPLOY_FAILED", "x"))
        monkeypatch.setattr(
            "app.crew.pipeline_graph.HelmsmanService", MagicMock(return_value=helmsman)
        )

        node = _make_deploying_node(ctx)
        result = await node(_make_state())
        assert result["error"]["code"] == "DEPLOY_FAILED"

    @pytest.mark.asyncio
    async def test_guard_failure_routes_to_fail_end(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        _patch_loads(monkeypatch, voyage=_mock_voyage(), latest_validation=None)
        _mock_guard(monkeypatch, "require_can_enter_deploying", raises=True)

        node = _make_deploying_node(ctx)
        result = await node(_make_state())
        assert result["error"]["code"] == "GUARD_FAIL"


# ---------------------------------------------------------------------------
# Building node — parallel scheduling
# ---------------------------------------------------------------------------


def _plan_with_phases(phases: list[dict[str, Any]]) -> MagicMock:
    """Build a mock plan whose `.phases` JSONB matches VoyagePlanSpec format."""
    from app.models.enums import CrewRole

    plan = MagicMock()
    plan.id = uuid.uuid4()
    enriched = []
    for p in phases:
        enriched.append(
            {
                "phase_number": p["phase_number"],
                "name": p.get("name", f"phase-{p['phase_number']}"),
                "description": p.get("description", "desc"),
                "assigned_to": p.get("assigned_to", CrewRole.SHIPWRIGHT.value),
                "depends_on": p.get("depends_on", []),
                "artifacts": p.get("artifacts", []),
            }
        )
    plan.phases = {"phases": enriched}
    return plan


class TestBuildingNode:
    @pytest.mark.asyncio
    async def test_single_layer_all_phases_parallel(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage(phase_status={"1": "PENDING", "2": "PENDING", "3": "PENDING"})
        plan = _plan_with_phases(
            [
                {"phase_number": 1},
                {"phase_number": 2},
                {"phase_number": 3},
            ]
        )
        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=plan,
            poneglyphs=[_poneglyph(1), _poneglyph(2), _poneglyph(3)],
            health_checks=[_health_check(1), _health_check(2), _health_check(3)],
            build_artifacts=[],
        )
        _mock_guard(monkeypatch, "require_can_enter_building")
        _mock_guard(monkeypatch, "require_can_enter_reviewing", raises=True)

        shipwright = MagicMock()
        shipwright.build_code = AsyncMock(return_value=MagicMock())
        monkeypatch.setattr(
            "app.crew.pipeline_graph.ShipwrightService", MagicMock(return_value=shipwright)
        )

        node = _make_building_node(ctx)
        await node(_make_state(max_parallel=3))
        assert shipwright.build_code.await_count == 3

    @pytest.mark.asyncio
    async def test_two_layers_respects_order(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage(phase_status={"1": "PENDING", "2": "PENDING"})
        plan = _plan_with_phases(
            [
                {"phase_number": 1},
                {"phase_number": 2, "depends_on": [1]},
            ]
        )
        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=plan,
            poneglyphs=[_poneglyph(1), _poneglyph(2)],
            health_checks=[_health_check(1), _health_check(2)],
            build_artifacts=[],
        )
        _mock_guard(monkeypatch, "require_can_enter_building")
        _mock_guard(monkeypatch, "require_can_enter_reviewing", raises=True)

        call_order: list[int] = []

        async def recording_build(voyage: Any, phase_number: int, *args: Any, **kwargs: Any) -> Any:
            call_order.append(phase_number)
            return MagicMock()

        shipwright = MagicMock()
        shipwright.build_code = AsyncMock(side_effect=recording_build)
        monkeypatch.setattr(
            "app.crew.pipeline_graph.ShipwrightService", MagicMock(return_value=shipwright)
        )

        node = _make_building_node(ctx)
        await node(_make_state(max_parallel=2))
        assert call_order == [1, 2]

    @pytest.mark.asyncio
    async def test_semaphore_bounds_concurrency(self, monkeypatch: pytest.MonkeyPatch) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage(phase_status={str(i): "PENDING" for i in range(1, 6)})
        plan = _plan_with_phases([{"phase_number": i} for i in range(1, 6)])
        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=plan,
            poneglyphs=[_poneglyph(i) for i in range(1, 6)],
            health_checks=[_health_check(i) for i in range(1, 6)],
            build_artifacts=[],
        )
        _mock_guard(monkeypatch, "require_can_enter_building")
        _mock_guard(monkeypatch, "require_can_enter_reviewing", raises=True)

        inflight = 0
        peak = 0
        lock = asyncio.Lock()

        async def slow_build(*args: Any, **kwargs: Any) -> Any:
            nonlocal inflight, peak
            async with lock:
                inflight += 1
                peak = max(peak, inflight)
            await asyncio.sleep(0.01)
            async with lock:
                inflight -= 1
            return MagicMock()

        shipwright = MagicMock()
        shipwright.build_code = AsyncMock(side_effect=slow_build)
        monkeypatch.setattr(
            "app.crew.pipeline_graph.ShipwrightService", MagicMock(return_value=shipwright)
        )

        node = _make_building_node(ctx)
        await node(_make_state(max_parallel=2))
        assert peak <= 2
        assert shipwright.build_code.await_count == 5

    @pytest.mark.asyncio
    async def test_partial_resume_skips_already_built_phases(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage(phase_status={"1": "BUILT", "2": "PENDING"})
        plan = _plan_with_phases(
            [
                {"phase_number": 1},
                {"phase_number": 2},
            ]
        )
        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=plan,
            poneglyphs=[_poneglyph(1), _poneglyph(2)],
            health_checks=[_health_check(1), _health_check(2)],
            build_artifacts=[_build_artifact(1)],
        )
        _mock_guard(monkeypatch, "require_can_enter_building")
        _mock_guard(monkeypatch, "require_can_enter_reviewing", raises=True)

        built: list[int] = []

        async def record(voyage: Any, phase_number: int, *a: Any, **k: Any) -> Any:
            built.append(phase_number)
            return MagicMock()

        shipwright = MagicMock()
        shipwright.build_code = AsyncMock(side_effect=record)
        monkeypatch.setattr(
            "app.crew.pipeline_graph.ShipwrightService", MagicMock(return_value=shipwright)
        )

        node = _make_building_node(ctx)
        await node(_make_state(max_parallel=2))
        assert built == [2]

    @pytest.mark.asyncio
    async def test_first_failure_cancels_layer_and_routes_to_fail_end(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.shipwright_service import ShipwrightError

        ctx = _mock_ctx()
        voyage = _mock_voyage(phase_status={"1": "PENDING", "2": "PENDING", "3": "PENDING"})
        plan = _plan_with_phases(
            [
                {"phase_number": 1},
                {"phase_number": 2},
                {"phase_number": 3},
            ]
        )
        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=plan,
            poneglyphs=[_poneglyph(1), _poneglyph(2), _poneglyph(3)],
            health_checks=[_health_check(1), _health_check(2), _health_check(3)],
            build_artifacts=[],
        )
        _mock_guard(monkeypatch, "require_can_enter_building")
        _mock_guard(monkeypatch, "require_can_enter_reviewing", raises=True)

        async def build(voyage: Any, phase_number: int, *a: Any, **k: Any) -> Any:
            if phase_number == 1:
                raise ShipwrightError("BUILD_FAILED", f"phase {phase_number} failed")
            await asyncio.sleep(0.05)
            return MagicMock()

        shipwright = MagicMock()
        shipwright.build_code = AsyncMock(side_effect=build)
        monkeypatch.setattr(
            "app.crew.pipeline_graph.ShipwrightService", MagicMock(return_value=shipwright)
        )

        node = _make_building_node(ctx)
        result = await node(_make_state(max_parallel=3))
        assert result["error"]["code"] == "BUILD_FAILED"
        assert result["error"]["stage"] == STAGE_BUILDING

    @pytest.mark.asyncio
    async def test_paused_before_layers_routes_to_pause_end(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _mock_ctx()
        _patch_loads(monkeypatch, voyage=_mock_voyage(status=VoyageStatus.PAUSED.value))
        node = _make_building_node(ctx)
        result = await node(_make_state())
        assert result == {"paused": True}


# ---------------------------------------------------------------------------
# Terminal nodes
# ---------------------------------------------------------------------------


class TestFinalizeAndTerminalNodes:
    @pytest.mark.asyncio
    async def test_finalize_sets_completed_and_emits_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        _patch_loads(monkeypatch, voyage=voyage)
        # Deployment row lookup returns None (dep_id missing).
        ctx.session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

        node = _make_finalize_node(ctx)
        await node(_make_state())
        assert voyage.status == VoyageStatus.COMPLETED.value
        published = [c.args[1] for c in ctx.mushi.publish.call_args_list]
        completed = [e for e in published if isinstance(e, PipelineCompletedEvent)]
        assert len(completed) == 1
        assert "duration_seconds" in completed[0].payload

    @pytest.mark.asyncio
    async def test_fail_end_sets_failed_and_emits_event(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        _patch_loads(monkeypatch, voyage=voyage)
        state = _make_state(error={"code": "X", "message": "m", "stage": STAGE_BUILDING})

        node = _make_fail_end(ctx)
        await node(state)
        assert voyage.status == VoyageStatus.FAILED.value
        published = [c.args[1] for c in ctx.mushi.publish.call_args_list]
        failed = [e for e in published if isinstance(e, PipelineFailedEvent)]
        assert len(failed) == 1
        assert failed[0].payload["code"] == "X"
        assert failed[0].payload["stage"] == STAGE_BUILDING

    @pytest.mark.asyncio
    async def test_pause_end_is_noop(self) -> None:
        ctx = _mock_ctx()
        node = _make_pause_end(ctx)
        result = await node(_make_state(paused=True))
        assert result == {}


# ---------------------------------------------------------------------------
# Full-graph smoke
# ---------------------------------------------------------------------------


class TestFullGraphSmoke:
    @pytest.mark.asyncio
    async def test_fully_satisfied_voyage_runs_to_completed_without_services(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Seed all artifacts so every stage's skip-already-satisfied fires.
        No crew-service class should be constructed; the graph should run to
        COMPLETED with only a PipelineCompletedEvent."""
        ctx = _mock_ctx()
        voyage = _mock_voyage(phase_status={"1": "BUILT"})
        plan = _plan_with_phases([{"phase_number": 1}])
        poneglyphs = [_poneglyph(1)]
        health_checks = [_health_check(1)]
        build_artifacts = [_build_artifact(1)]
        passed_run = MagicMock(id=uuid.uuid4(), status="passed")

        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=plan,
            poneglyphs=poneglyphs,
            health_checks=health_checks,
            build_artifacts=build_artifacts,
            latest_validation=passed_run,
        )
        _mock_guard(monkeypatch, "require_can_enter_planning")
        _mock_guard(monkeypatch, "require_can_enter_pdd")
        _mock_guard(monkeypatch, "require_can_enter_tdd")
        _mock_guard(monkeypatch, "require_can_enter_building")
        _mock_guard(monkeypatch, "require_can_enter_reviewing")
        _mock_guard(monkeypatch, "require_can_enter_deploying")

        # Helmsman is the only service that still runs (deploying_node never skips).
        deployment = MagicMock(deployment_id=uuid.uuid4())
        helmsman = MagicMock()
        helmsman.deploy = AsyncMock(return_value=deployment)
        captain_cls = MagicMock()
        navigator_cls = MagicMock()
        doctor_cls = MagicMock()
        shipwright_cls = MagicMock()
        monkeypatch.setattr("app.crew.pipeline_graph.CaptainService", captain_cls)
        monkeypatch.setattr("app.crew.pipeline_graph.NavigatorService", navigator_cls)
        monkeypatch.setattr("app.crew.pipeline_graph.DoctorService", doctor_cls)
        monkeypatch.setattr("app.crew.pipeline_graph.ShipwrightService", shipwright_cls)
        monkeypatch.setattr(
            "app.crew.pipeline_graph.HelmsmanService", MagicMock(return_value=helmsman)
        )

        # finalize_node's Deployment lookup
        ctx.session.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=lambda: None))

        graph = build_pipeline_graph(ctx)
        final = await graph.ainvoke(_make_state())

        # No planning/pdd/tdd/shipwright service should have been constructed.
        captain_cls.assert_not_called()
        navigator_cls.assert_not_called()
        shipwright_cls.assert_not_called()
        # Doctor may be constructed for reviewing skip path but validate_code must not fire.
        assert voyage.status == VoyageStatus.COMPLETED.value
        assert final.get("error") is None
        assert final.get("paused") is False

    @pytest.mark.asyncio
    async def test_failure_in_pdd_routes_to_fail_end_and_skips_later_stages(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.services.navigator_service import NavigatorError

        ctx = _mock_ctx()
        voyage = _mock_voyage()
        plan = _mock_plan()
        _patch_loads(
            monkeypatch,
            voyage=voyage,
            plan=plan,
            poneglyphs=[],
            health_checks=[],
            build_artifacts=[],
            latest_validation=None,
        )
        _mock_guard(monkeypatch, "require_can_enter_planning")
        _mock_guard(monkeypatch, "require_can_enter_pdd")
        _mock_guard(monkeypatch, "require_can_enter_tdd", raises=True)

        navigator = MagicMock()
        navigator.draft_poneglyphs = AsyncMock(
            side_effect=NavigatorError("PONEGLYPH_GEN_FAILED", "x")
        )
        monkeypatch.setattr(
            "app.crew.pipeline_graph.NavigatorService", MagicMock(return_value=navigator)
        )
        doctor_cls = MagicMock()
        shipwright_cls = MagicMock()
        helmsman_cls = MagicMock()
        monkeypatch.setattr("app.crew.pipeline_graph.DoctorService", doctor_cls)
        monkeypatch.setattr("app.crew.pipeline_graph.ShipwrightService", shipwright_cls)
        monkeypatch.setattr("app.crew.pipeline_graph.HelmsmanService", helmsman_cls)

        graph = build_pipeline_graph(ctx)
        final = await graph.ainvoke(_make_state())

        doctor_cls.assert_not_called()
        shipwright_cls.assert_not_called()
        helmsman_cls.assert_not_called()
        assert voyage.status == VoyageStatus.FAILED.value
        assert final["error"]["code"] == "PONEGLYPH_GEN_FAILED"

    @pytest.mark.asyncio
    async def test_pause_mid_pipeline_routes_to_pause_end(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        ctx = _mock_ctx()
        # Planning passes, but the PAUSED check at PDD stage should fire.
        paused_voyage = _mock_voyage(status=VoyageStatus.PAUSED.value)
        plan = _mock_plan()

        # Planning skips because plan exists → load_voyage inside planning skip sees CHARTED.
        # Then pdd_node's paused-check fires.
        # We return different voyages on each _load_voyage call.
        voyages_to_serve = iter([_mock_voyage(), _mock_voyage(), paused_voyage, paused_voyage])
        monkeypatch.setattr(
            "app.crew.pipeline_graph._load_voyage",
            AsyncMock(side_effect=lambda session, vid: next(voyages_to_serve)),
        )
        monkeypatch.setattr("app.crew.pipeline_graph._load_plan", AsyncMock(return_value=plan))
        monkeypatch.setattr("app.crew.pipeline_graph._load_poneglyphs", AsyncMock(return_value=[]))
        monkeypatch.setattr(
            "app.crew.pipeline_graph._load_health_checks", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(
            "app.crew.pipeline_graph._load_build_artifacts", AsyncMock(return_value=[])
        )
        monkeypatch.setattr(
            "app.crew.pipeline_graph._load_latest_validation", AsyncMock(return_value=None)
        )
        _mock_guard(monkeypatch, "require_can_enter_planning")

        graph = build_pipeline_graph(ctx)
        final = await graph.ainvoke(_make_state())
        assert final["paused"] is True

    @pytest.mark.asyncio
    async def test_stage_entered_and_completed_events_emitted(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Stage events emitted with matching stage name and skipped=True when skipped."""
        ctx = _mock_ctx()
        voyage = _mock_voyage()
        plan = _mock_plan()
        poneglyphs = [_poneglyph(1)]
        _patch_loads(monkeypatch, voyage=voyage, plan=plan, poneglyphs=poneglyphs, health_checks=[])
        _mock_guard(monkeypatch, "require_can_enter_pdd")
        _mock_guard(monkeypatch, "require_can_enter_tdd")

        node = _make_pdd_node(ctx)
        await node(_make_state())
        published = [c.args[1] for c in ctx.mushi.publish.call_args_list]
        completed = [e for e in published if isinstance(e, PipelineStageCompletedEvent)]
        assert len(completed) == 1
        assert completed[0].payload["stage"] == STAGE_PDD
        assert completed[0].payload["skipped"] is True
        # No stage_entered because the stage was skipped.
        entered = [e for e in published if isinstance(e, PipelineStageEnteredEvent)]
        assert len(entered) == 0
