"""Tests for ShipwrightService (mocked dependencies)."""

from __future__ import annotations

import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.models.build_artifact import BuildArtifact
from app.models.enums import VoyageStatus
from app.models.shipwright_run import ShipwrightRun
from app.models.vivre_card import VivreCard
from app.schemas.shipwright import BuildArtifactSpec
from app.services.shipwright_service import (
    PHASE_STATUS_BUILDING,
    PHASE_STATUS_BUILT,
    PHASE_STATUS_FAILED,
    PHASE_STATUS_PENDING,
    SHIPWRIGHT_MAX_ITERATIONS,
    ShipwrightError,
    ShipwrightService,
)

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()
PONEGLYPH_ID = uuid.uuid4()


def _mock_voyage(
    status: str = VoyageStatus.CHARTED.value,
    target_repo: str | None = None,
    phase_status: dict[str, str] | None = None,
) -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    voyage.user_id = USER_ID
    voyage.status = status
    voyage.target_repo = target_repo
    voyage.phase_status = phase_status if phase_status is not None else {}
    return voyage


def _mock_poneglyph(
    phase_number: int = 1,
    malformed: bool = False,
) -> MagicMock:
    p = MagicMock()
    p.id = PONEGLYPH_ID
    p.voyage_id = VOYAGE_ID
    p.phase_number = phase_number
    if malformed:
        p.content = "not-json{{{"
    else:
        p.content = json.dumps(
            {
                "phase_number": phase_number,
                "title": f"Phase {phase_number}",
                "task_description": "Build the thing",
                "test_criteria": ["works"],
                "file_paths": [f"src/phase{phase_number}.py"],
            }
        )
    return p


def _mock_health_check(phase_number: int = 1, framework: str = "pytest") -> MagicMock:
    hc = MagicMock()
    hc.id = uuid.uuid4()
    hc.phase_number = phase_number
    hc.file_path = f"tests/test_phase{phase_number}.py"
    hc.content = f"def test_p{phase_number}(): assert False"
    hc.framework = framework
    return hc


def _graph_state(
    *,
    exit_code: int = 0,
    error: str | None = None,
    stdout: str = "1 passed",
    passed: int = 1,
    failed: int = 0,
    total: int = 1,
    generated_files: list[BuildArtifactSpec] | None = None,
    phase_number: int = 1,
) -> dict[str, Any]:
    if generated_files is None:
        generated_files = [
            BuildArtifactSpec(
                file_path=f"src/phase{phase_number}.py",
                content="def run(): return True",
                language="python",
            )
        ]
    return {
        "voyage_id": VOYAGE_ID,
        "user_id": USER_ID,
        "phase_number": phase_number,
        "poneglyph": {},
        "health_checks": [],
        "iteration": 1,
        "last_test_output": None,
        "raw_output": "{}",
        "generated_files": None if error else generated_files,
        "exit_code": None if error else exit_code,
        "stdout": stdout,
        "passed_count": passed,
        "failed_count": failed,
        "total_count": total,
        "error": error,
    }


@pytest.fixture
def mock_dial_router() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_mushi() -> AsyncMock:
    mushi = AsyncMock()
    mushi.publish = AsyncMock(return_value="msg-1")
    return mushi


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.flush = AsyncMock()
    session.commit = AsyncMock()
    session.refresh = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalars.return_value.all.return_value = []
    result_mock.scalars.return_value.first.return_value = None
    session.execute = AsyncMock(return_value=result_mock)
    return session


@pytest.fixture
def mock_execution() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_git() -> AsyncMock:
    git = AsyncMock()
    git.create_branch = AsyncMock()
    git.commit = AsyncMock()
    git.push = AsyncMock()
    return git


@pytest.fixture
def service(
    mock_dial_router: AsyncMock,
    mock_mushi: AsyncMock,
    mock_session: AsyncMock,
    mock_execution: AsyncMock,
    mock_git: AsyncMock,
) -> ShipwrightService:
    svc = ShipwrightService(mock_dial_router, mock_mushi, mock_session, mock_execution, mock_git)
    svc._graph = AsyncMock()  # type: ignore[assignment]
    svc._graph.ainvoke = AsyncMock(return_value=_graph_state())  # type: ignore[attr-defined]
    return svc


class TestPhaseStatusConstants:
    def test_constants_have_expected_values(self) -> None:
        assert PHASE_STATUS_PENDING == "PENDING"
        assert PHASE_STATUS_BUILDING == "BUILDING"
        assert PHASE_STATUS_BUILT == "BUILT"
        assert PHASE_STATUS_FAILED == "FAILED"


class TestBuildCodeGate:
    @pytest.mark.asyncio
    async def test_pending_phase_is_buildable(self, service: ShipwrightService) -> None:
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_PENDING})
        result = await service.build_code(
            voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_missing_phase_key_is_buildable(self, service: ShipwrightService) -> None:
        voyage = _mock_voyage(phase_status={})
        result = await service.build_code(
            voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_failed_phase_is_rebuildable(self, service: ShipwrightService) -> None:
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_FAILED})
        result = await service.build_code(
            voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_building_phase_raises_phase_not_buildable(
        self, service: ShipwrightService
    ) -> None:
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_BUILDING})
        with pytest.raises(ShipwrightError) as exc_info:
            await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert exc_info.value.code == "PHASE_NOT_BUILDABLE"
        service._graph.ainvoke.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_built_phase_raises_phase_not_buildable(self, service: ShipwrightService) -> None:
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_BUILT})
        with pytest.raises(ShipwrightError) as exc_info:
            await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert exc_info.value.code == "PHASE_NOT_BUILDABLE"
        service._graph.ainvoke.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_vitest_check_precedes_phase_gate(self, service: ShipwrightService) -> None:
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_BUILT})
        with pytest.raises(ShipwrightError) as exc_info:
            await service.build_code(
                voyage,
                1,
                _mock_poneglyph(),
                [_mock_health_check(framework="vitest")],
                USER_ID,
            )
        assert exc_info.value.code == "VITEST_NOT_SUPPORTED"


class TestPhaseStatusTransitions:
    @pytest.mark.asyncio
    async def test_success_transitions_pending_to_built(self, service: ShipwrightService) -> None:
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_PENDING})
        await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert voyage.phase_status["1"] == PHASE_STATUS_BUILT

    @pytest.mark.asyncio
    async def test_max_iterations_transitions_to_failed(self, service: ShipwrightService) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[_graph_state(exit_code=1, stdout="boom")] * SHIPWRIGHT_MAX_ITERATIONS
        )
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_PENDING})
        await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert voyage.phase_status["1"] == PHASE_STATUS_FAILED

    @pytest.mark.asyncio
    async def test_parse_failure_transitions_to_failed(self, service: ShipwrightService) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[_graph_state(error="parse failed")] * SHIPWRIGHT_MAX_ITERATIONS
        )
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_PENDING})
        with pytest.raises(ShipwrightError):
            await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert voyage.phase_status["1"] == PHASE_STATUS_FAILED

    @pytest.mark.asyncio
    async def test_does_not_touch_voyage_status(self, service: ShipwrightService) -> None:
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_PENDING})
        await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert voyage.status == VoyageStatus.CHARTED.value

    @pytest.mark.asyncio
    async def test_does_not_touch_voyage_status_on_failure(
        self, service: ShipwrightService
    ) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[_graph_state(exit_code=1)] * SHIPWRIGHT_MAX_ITERATIONS
        )
        voyage = _mock_voyage(phase_status={"1": PHASE_STATUS_PENDING})
        await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert voyage.status == VoyageStatus.CHARTED.value

    @pytest.mark.asyncio
    async def test_preserves_other_phase_statuses_on_success(
        self, service: ShipwrightService
    ) -> None:
        voyage = _mock_voyage(
            phase_status={
                "1": PHASE_STATUS_PENDING,
                "2": PHASE_STATUS_BUILT,
                "3": PHASE_STATUS_FAILED,
            }
        )
        await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert voyage.phase_status["1"] == PHASE_STATUS_BUILT
        assert voyage.phase_status["2"] == PHASE_STATUS_BUILT
        assert voyage.phase_status["3"] == PHASE_STATUS_FAILED

    @pytest.mark.asyncio
    async def test_preserves_other_phase_statuses_on_failure(
        self, service: ShipwrightService
    ) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[_graph_state(exit_code=1)] * SHIPWRIGHT_MAX_ITERATIONS
        )
        voyage = _mock_voyage(
            phase_status={
                "1": PHASE_STATUS_PENDING,
                "2": PHASE_STATUS_BUILT,
            }
        )
        await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert voyage.phase_status["1"] == PHASE_STATUS_FAILED
        assert voyage.phase_status["2"] == PHASE_STATUS_BUILT


class TestBuildCodeHappyPath:
    @pytest.mark.asyncio
    async def test_invokes_graph_on_iteration_one(self, service: ShipwrightService) -> None:
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        first_state = service._graph.ainvoke.call_args_list[0].args[0]  # type: ignore[attr-defined]
        assert first_state["iteration"] == 1

    @pytest.mark.asyncio
    async def test_terminates_loop_on_first_green(self, service: ShipwrightService) -> None:
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        assert service._graph.ainvoke.await_count == 1  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_persists_shipwright_run_with_passed_status(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        added = [c.args[0] for c in mock_session.add.call_args_list]
        runs = [o for o in added if isinstance(o, ShipwrightRun)]
        assert len(runs) == 1
        assert runs[0].status == "passed"
        assert runs[0].iteration_count == 1

    @pytest.mark.asyncio
    async def test_deletes_existing_build_artifacts_scoped_to_phase(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        from sqlalchemy.sql.dml import Delete

        await service.build_code(
            _mock_voyage(), 2, _mock_poneglyph(phase_number=2), [_mock_health_check(2)], USER_ID
        )
        executed = [c.args[0] for c in mock_session.execute.call_args_list]
        deletes = [s for s in executed if isinstance(s, Delete)]
        assert len(deletes) == 1
        compiled = str(deletes[0].compile(compile_kwargs={"literal_binds": True}))
        assert "phase_number = 2" in compiled

    @pytest.mark.asyncio
    async def test_persists_one_build_artifact_per_generated_file(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        files = [
            BuildArtifactSpec(file_path="a.py", content="x", language="python"),
            BuildArtifactSpec(file_path="b.py", content="y", language="python"),
        ]
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            return_value=_graph_state(generated_files=files)
        )
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        added = [c.args[0] for c in mock_session.add.call_args_list]
        artifacts = [o for o in added if isinstance(o, BuildArtifact)]
        assert len(artifacts) == 2

    @pytest.mark.asyncio
    async def test_creates_build_complete_vivre_card(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        added = [c.args[0] for c in mock_session.add.call_args_list]
        cards = [o for o in added if isinstance(o, VivreCard)]
        reasons = [c.checkpoint_reason for c in cards]
        assert "build_complete" in reasons

    @pytest.mark.asyncio
    async def test_creates_iteration_vivre_card_per_iteration(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        added = [c.args[0] for c in mock_session.add.call_args_list]
        cards = [o for o in added if isinstance(o, VivreCard)]
        iter_cards = [c for c in cards if c.checkpoint_reason == "iteration"]
        assert len(iter_cards) == 1

    @pytest.mark.asyncio
    async def test_commits_exactly_once(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_publishes_code_generated_and_tests_passed_events(
        self, service: ShipwrightService, mock_mushi: AsyncMock
    ) -> None:
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        events = [c.args[1] for c in mock_mushi.publish.call_args_list]
        types = {e.event_type for e in events}
        assert {"code_generated", "tests_passed"} == types

    @pytest.mark.asyncio
    async def test_succeeds_when_event_publish_fails(
        self, service: ShipwrightService, mock_mushi: AsyncMock
    ) -> None:
        mock_mushi.publish.side_effect = ConnectionError("Redis down")
        result = await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_calls_git_when_target_repo_set(
        self, service: ShipwrightService, mock_git: AsyncMock
    ) -> None:
        voyage = _mock_voyage(target_repo="https://github.com/org/repo.git")
        await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        mock_git.create_branch.assert_awaited_once()
        mock_git.commit.assert_awaited_once()
        mock_git.push.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_succeeds_when_git_commit_fails(
        self, service: ShipwrightService, mock_git: AsyncMock
    ) -> None:
        mock_git.commit.side_effect = RuntimeError("git boom")
        voyage = _mock_voyage(target_repo="https://github.com/org/repo.git")
        result = await service.build_code(
            voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        assert result.status == "passed"

    @pytest.mark.asyncio
    async def test_skips_git_when_no_git_service(
        self,
        mock_dial_router: AsyncMock,
        mock_mushi: AsyncMock,
        mock_session: AsyncMock,
        mock_execution: AsyncMock,
    ) -> None:
        svc = ShipwrightService(
            mock_dial_router,
            mock_mushi,
            mock_session,
            mock_execution,
            git_service=None,
        )
        svc._graph = AsyncMock()  # type: ignore[assignment]
        svc._graph.ainvoke = AsyncMock(return_value=_graph_state())  # type: ignore[attr-defined]

        voyage = _mock_voyage(target_repo="https://github.com/org/repo.git")
        result = await svc.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert result.status == "passed"


class TestBuildCodeIterationLoop:
    @pytest.mark.asyncio
    async def test_retries_with_last_test_output_on_failure(
        self, service: ShipwrightService
    ) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[
                _graph_state(exit_code=1, stdout="pytest failure output"),
                _graph_state(exit_code=0, stdout="1 passed"),
            ]
        )
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        assert service._graph.ainvoke.await_count == 2  # type: ignore[attr-defined]
        second_state = service._graph.ainvoke.call_args_list[1].args[0]  # type: ignore[attr-defined]
        assert second_state["iteration"] == 2
        assert second_state["last_test_output"] == "pytest failure output"

    @pytest.mark.asyncio
    async def test_max_iterations_when_all_fail(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        fail_state = _graph_state(exit_code=1, stdout="boom")
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[fail_state] * SHIPWRIGHT_MAX_ITERATIONS
        )
        result = await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        assert result.status == "max_iterations"
        assert result.iteration_count == SHIPWRIGHT_MAX_ITERATIONS

    @pytest.mark.asyncio
    async def test_no_artifacts_on_max_iterations(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[_graph_state(exit_code=1)] * SHIPWRIGHT_MAX_ITERATIONS
        )
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        added = [c.args[0] for c in mock_session.add.call_args_list]
        artifacts = [o for o in added if isinstance(o, BuildArtifact)]
        assert artifacts == []

    @pytest.mark.asyncio
    async def test_no_events_on_max_iterations(
        self, service: ShipwrightService, mock_mushi: AsyncMock
    ) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[_graph_state(exit_code=1)] * SHIPWRIGHT_MAX_ITERATIONS
        )
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        mock_mushi.publish.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_persists_max_iterations_run(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[_graph_state(exit_code=1)] * SHIPWRIGHT_MAX_ITERATIONS
        )
        await service.build_code(
            _mock_voyage(), 1, _mock_poneglyph(), [_mock_health_check()], USER_ID
        )
        added = [c.args[0] for c in mock_session.add.call_args_list]
        runs = [o for o in added if isinstance(o, ShipwrightRun)]
        assert len(runs) == 1
        assert runs[0].status == "max_iterations"
        assert runs[0].iteration_count == SHIPWRIGHT_MAX_ITERATIONS


class TestBuildCodeErrorPaths:
    @pytest.mark.asyncio
    async def test_raises_vitest_not_supported(self, service: ShipwrightService) -> None:
        voyage = _mock_voyage()
        with pytest.raises(ShipwrightError) as exc_info:
            await service.build_code(
                voyage,
                1,
                _mock_poneglyph(),
                [_mock_health_check(framework="vitest")],
                USER_ID,
            )
        assert exc_info.value.code == "VITEST_NOT_SUPPORTED"
        service._graph.ainvoke.assert_not_awaited()  # type: ignore[attr-defined]

    @pytest.mark.asyncio
    async def test_raises_build_parse_failed_when_graph_errors(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        service._graph.ainvoke = AsyncMock(  # type: ignore[attr-defined]
            side_effect=[_graph_state(error="parse failed")] * SHIPWRIGHT_MAX_ITERATIONS
        )
        voyage = _mock_voyage()
        with pytest.raises(ShipwrightError) as exc_info:
            await service.build_code(voyage, 1, _mock_poneglyph(), [_mock_health_check()], USER_ID)
        assert exc_info.value.code == "BUILD_PARSE_FAILED"
        added = [c.args[0] for c in mock_session.add.call_args_list]
        runs = [o for o in added if isinstance(o, ShipwrightRun)]
        assert len(runs) == 1
        assert runs[0].status == "failed"
        assert runs[0].iteration_count == SHIPWRIGHT_MAX_ITERATIONS
        assert not [o for o in added if isinstance(o, BuildArtifact)]
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_malformed_poneglyph_degrades_gracefully(
        self, service: ShipwrightService, caplog: pytest.LogCaptureFixture
    ) -> None:
        import logging

        with caplog.at_level(logging.WARNING, logger="app.services.shipwright_service"):
            result = await service.build_code(
                _mock_voyage(),
                1,
                _mock_poneglyph(malformed=True),
                [_mock_health_check()],
                USER_ID,
            )
        assert result.status == "passed"
        assert any("malformed" in r.message for r in caplog.records)


class TestGetBuildArtifacts:
    @pytest.mark.asyncio
    async def test_returns_ordered_rows(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        a1, a2 = MagicMock(), MagicMock()
        a1.phase_number, a2.phase_number = 1, 2
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = [a1, a2]
        mock_session.execute.return_value = result_mock

        result = await service.get_build_artifacts(VOYAGE_ID)
        assert len(result) == 2

    @pytest.mark.asyncio
    async def test_filters_by_phase_number(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        from sqlalchemy.sql.selectable import Select

        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        mock_session.execute.return_value = result_mock

        await service.get_build_artifacts(VOYAGE_ID, phase_number=2)
        stmt = mock_session.execute.call_args.args[0]
        assert isinstance(stmt, Select)
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "phase_number = 2" in compiled

    @pytest.mark.asyncio
    async def test_returns_empty_list(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        result = await service.get_build_artifacts(VOYAGE_ID)
        assert result == []

    @pytest.mark.asyncio
    async def test_reader_instance_works(self) -> None:
        session = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalars.return_value.all.return_value = []
        session.execute = AsyncMock(return_value=result_mock)

        reader = ShipwrightService.reader(session)
        result = await reader.get_build_artifacts(VOYAGE_ID)
        assert result == []


class TestGetLatestRun:
    @pytest.mark.asyncio
    async def test_returns_most_recent_row(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        run = MagicMock()
        run.phase_number = 1
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = run
        mock_session.execute.return_value = result_mock

        result = await service.get_latest_run(VOYAGE_ID, 1)
        assert result is run

    @pytest.mark.asyncio
    async def test_returns_none_when_no_row(
        self, service: ShipwrightService, mock_session: AsyncMock
    ) -> None:
        result_mock = MagicMock()
        result_mock.scalars.return_value.first.return_value = None
        mock_session.execute.return_value = result_mock

        result = await service.get_latest_run(VOYAGE_ID, 1)
        assert result is None
