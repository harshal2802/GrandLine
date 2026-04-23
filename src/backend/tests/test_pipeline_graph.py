"""Tests for the master Voyage Pipeline graph — topological scheduler,
build_pipeline_graph compilation, and the PipelineState shape."""

from __future__ import annotations

import uuid
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
    _route_after_stage,
    build_pipeline_graph,
    topological_layers,
)
from app.services.pipeline_guards import PipelineError


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
        # 1 -> 2, 1 -> 3, {2,3} -> 4
        phases = [
            {"phase_number": 1, "depends_on": []},
            {"phase_number": 2, "depends_on": [1]},
            {"phase_number": 3, "depends_on": [1]},
            {"phase_number": 4, "depends_on": [2, 3]},
        ]
        assert topological_layers(phases) == [[1], [2, 3], [4]]

    def test_mixed_parallel_and_chain(self) -> None:
        # 1 independent, 2 depends on nothing, 3 depends on 1, 4 depends on 2+3
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
        return {
            "voyage_id": uuid.uuid4(),
            "user_id": uuid.uuid4(),
            "deploy_tier": "preview",
            "max_parallel_shipwrights": 1,
            "task": "t",
            "plan_id": None,
            "poneglyph_count": 0,
            "health_check_count": 0,
            "build_artifact_count": 0,
            "validation_run_id": None,
            "deployment_id": None,
            "error": error,
            "paused": paused,
        }

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
        ctx = PipelineContext(
            session=AsyncMock(),
            mushi=AsyncMock(),
            dial_router=AsyncMock(),
            execution_service=AsyncMock(),
            git_service=None,
            deployment_backend=AsyncMock(),
        )
        graph = build_pipeline_graph(ctx)
        assert graph is not None

    def test_graph_has_all_expected_nodes(self) -> None:
        ctx = PipelineContext(
            session=AsyncMock(),
            mushi=AsyncMock(),
            dial_router=AsyncMock(),
            execution_service=AsyncMock(),
            git_service=None,
            deployment_backend=AsyncMock(),
        )
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
