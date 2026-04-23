"""Tests for PipelineService — orchestrates the full Voyage Pipeline."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.den_den_mushi.events import PipelineFailedEvent, PipelineStartedEvent
from app.models.enums import VoyageStatus
from app.services.pipeline_guards import PipelineError
from app.services.pipeline_service import PipelineService

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_voyage(
    status: str = VoyageStatus.CHARTED.value,
    phase_status: dict[str, str] | None = None,
) -> MagicMock:
    v = MagicMock()
    v.id = VOYAGE_ID
    v.status = status
    v.phase_status = phase_status if phase_status is not None else {}
    return v


@pytest.fixture
def mock_session() -> AsyncMock:
    session = AsyncMock()
    session.add = MagicMock()
    session.commit = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = None
    result_mock.scalar.return_value = 0
    session.execute = AsyncMock(return_value=result_mock)
    return session


@pytest.fixture
def mock_mushi() -> AsyncMock:
    m = AsyncMock()
    m.publish = AsyncMock(return_value="msg-1")
    return m


@pytest.fixture
def mock_dial_router() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_execution() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def mock_backend() -> AsyncMock:
    return AsyncMock()


@pytest.fixture
def service(
    mock_session: AsyncMock,
    mock_mushi: AsyncMock,
    mock_dial_router: AsyncMock,
    mock_execution: AsyncMock,
    mock_backend: AsyncMock,
) -> PipelineService:
    return PipelineService(
        session=mock_session,
        mushi=mock_mushi,
        dial_router=mock_dial_router,
        execution_service=mock_execution,
        git_service=None,
        deployment_backend=mock_backend,
    )


class TestStartGuardFailure:
    @pytest.mark.asyncio
    async def test_already_building_raises_pipeline_error(self, service: PipelineService) -> None:
        voyage = _mock_voyage(status=VoyageStatus.BUILDING.value)
        with pytest.raises(PipelineError) as exc:
            await service.start(voyage, USER_ID, "task")
        assert exc.value.code == "VOYAGE_NOT_PLANNABLE"

    @pytest.mark.asyncio
    async def test_completed_voyage_raises_pipeline_error(self, service: PipelineService) -> None:
        voyage = _mock_voyage(status=VoyageStatus.COMPLETED.value)
        with pytest.raises(PipelineError):
            await service.start(voyage, USER_ID, "task")


class TestStartHappyPath:
    @pytest.mark.asyncio
    async def test_publishes_pipeline_started(
        self,
        service: PipelineService,
        mock_mushi: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "voyage_id": VOYAGE_ID,
                "user_id": USER_ID,
                "deploy_tier": "preview",
                "max_parallel_shipwrights": 1,
                "task": "t",
                "plan_id": None,
                "poneglyph_count": 0,
                "health_check_count": 0,
                "build_artifact_count": 0,
                "validation_run_id": None,
                "deployment_id": None,
                "error": None,
                "paused": False,
            }
        )
        monkeypatch.setattr(
            "app.services.pipeline_service.build_pipeline_graph",
            lambda _ctx: mock_graph,
        )

        voyage = _mock_voyage()
        await service.start(voyage, USER_ID, "Build login")

        published = [c.args[1] for c in mock_mushi.publish.call_args_list]
        assert any(isinstance(e, PipelineStartedEvent) for e in published)

    @pytest.mark.asyncio
    async def test_paused_final_state_returns_without_raising(
        self,
        service: PipelineService,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "voyage_id": VOYAGE_ID,
                "user_id": USER_ID,
                "deploy_tier": "preview",
                "max_parallel_shipwrights": 1,
                "task": "t",
                "plan_id": None,
                "poneglyph_count": 0,
                "health_check_count": 0,
                "build_artifact_count": 0,
                "validation_run_id": None,
                "deployment_id": None,
                "error": None,
                "paused": True,
            }
        )
        monkeypatch.setattr(
            "app.services.pipeline_service.build_pipeline_graph",
            lambda _ctx: mock_graph,
        )
        voyage = _mock_voyage()
        await service.start(voyage, USER_ID, "task")


class TestStartFailurePath:
    @pytest.mark.asyncio
    async def test_error_in_final_state_raises_pipeline_error(
        self, service: PipelineService, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "voyage_id": VOYAGE_ID,
                "user_id": USER_ID,
                "deploy_tier": "preview",
                "max_parallel_shipwrights": 1,
                "task": "t",
                "plan_id": None,
                "poneglyph_count": 0,
                "health_check_count": 0,
                "build_artifact_count": 0,
                "validation_run_id": None,
                "deployment_id": None,
                "error": {
                    "code": "PHASE_NOT_BUILDABLE",
                    "message": "already built",
                    "stage": "BUILDING",
                },
                "paused": False,
            }
        )
        monkeypatch.setattr(
            "app.services.pipeline_service.build_pipeline_graph",
            lambda _ctx: mock_graph,
        )
        voyage = _mock_voyage()
        with pytest.raises(PipelineError) as exc:
            await service.start(voyage, USER_ID, "task")
        assert exc.value.code == "PHASE_NOT_BUILDABLE"

    @pytest.mark.asyncio
    async def test_graph_exception_publishes_pipeline_failed(
        self,
        service: PipelineService,
        mock_mushi: AsyncMock,
        mock_session: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(side_effect=RuntimeError("boom"))
        monkeypatch.setattr(
            "app.services.pipeline_service.build_pipeline_graph",
            lambda _ctx: mock_graph,
        )
        # stub the voyage reload in _mark_failed
        reload_voyage = _mock_voyage()
        reload_result = MagicMock()
        reload_result.scalar_one_or_none.return_value = reload_voyage
        empty_result = MagicMock()
        empty_result.scalar_one_or_none.return_value = None
        empty_result.scalar.return_value = 0
        # First call in _resolve_concurrency returns empty dial config;
        # next calls for _mark_failed return the voyage.
        mock_session.execute.side_effect = [empty_result, reload_result]
        voyage = _mock_voyage()
        with pytest.raises(PipelineError) as exc:
            await service.start(voyage, USER_ID, "task")
        assert exc.value.code == "PIPELINE_INTERNAL"

        published = [c.args[1] for c in mock_mushi.publish.call_args_list]
        assert any(isinstance(e, PipelineFailedEvent) for e in published)


class TestResolveConcurrency:
    @pytest.mark.asyncio
    async def test_override_within_bounds(self, service: PipelineService) -> None:
        result = await service._resolve_concurrency(VOYAGE_ID, 5)
        assert result == 5

    @pytest.mark.asyncio
    async def test_override_too_low_raises(self, service: PipelineService) -> None:
        with pytest.raises(PipelineError) as exc:
            await service._resolve_concurrency(VOYAGE_ID, 0)
        assert exc.value.code == "INVALID_CONCURRENCY"

    @pytest.mark.asyncio
    async def test_override_too_high_raises(self, service: PipelineService) -> None:
        with pytest.raises(PipelineError) as exc:
            await service._resolve_concurrency(VOYAGE_ID, 11)
        assert exc.value.code == "INVALID_CONCURRENCY"

    @pytest.mark.asyncio
    async def test_default_when_no_override_and_no_dial_config(
        self, service: PipelineService
    ) -> None:
        result = await service._resolve_concurrency(VOYAGE_ID, None)
        assert result == 1

    @pytest.mark.asyncio
    async def test_reads_from_dial_config_when_present(
        self, service: PipelineService, mock_session: AsyncMock
    ) -> None:
        dial_config = MagicMock()
        dial_config.role_mapping = {"shipwright": {"max_concurrency": 4}}
        result_mock = MagicMock()
        result_mock.scalar_one_or_none.return_value = dial_config
        mock_session.execute = AsyncMock(return_value=result_mock)
        result = await service._resolve_concurrency(VOYAGE_ID, None)
        assert result == 4


class TestPauseCancel:
    @pytest.mark.asyncio
    async def test_pause_sets_voyage_paused(
        self, service: PipelineService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage(status=VoyageStatus.BUILDING.value)
        await service.pause(voyage)
        assert voyage.status == VoyageStatus.PAUSED.value
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_pause_skips_terminal_status(
        self, service: PipelineService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage(status=VoyageStatus.COMPLETED.value)
        await service.pause(voyage)
        assert voyage.status == VoyageStatus.COMPLETED.value
        mock_session.commit.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_cancel_sets_voyage_cancelled(
        self, service: PipelineService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage(status=VoyageStatus.BUILDING.value)
        await service.cancel(voyage)
        assert voyage.status == VoyageStatus.CANCELLED.value
        mock_session.commit.assert_awaited()

    @pytest.mark.asyncio
    async def test_cancel_skips_failed_voyage(
        self, service: PipelineService, mock_session: AsyncMock
    ) -> None:
        voyage = _mock_voyage(status=VoyageStatus.FAILED.value)
        await service.cancel(voyage)
        mock_session.commit.assert_not_awaited()


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_returns_snapshot_with_counts(
        self, service: PipelineService, mock_session: AsyncMock
    ) -> None:
        count_result = MagicMock()
        count_result.scalar.return_value = 3

        val_result = MagicMock()
        latest_val = MagicMock()
        latest_val.status = "passed"
        val_result.scalar_one_or_none.return_value = latest_val

        dep_result = MagicMock()
        dep_result.scalar_one_or_none.return_value = None

        err_result = MagicMock()
        err_result.scalar_one_or_none.return_value = None

        # order of execute calls in get_status:
        # plan_exists, poneglyph_count, health_check_count,
        # build_artifact_count, latest_validation, latest_deployment, error_card
        mock_session.execute.side_effect = [
            count_result,
            count_result,
            count_result,
            count_result,
            val_result,
            dep_result,
            err_result,
        ]

        voyage = _mock_voyage(phase_status={"1": "BUILT"})
        snapshot = await service.get_status(voyage)
        assert snapshot.voyage_id == VOYAGE_ID
        assert snapshot.poneglyph_count == 3
        assert snapshot.plan_exists is True
        assert snapshot.last_validation_status == "passed"
        assert snapshot.phase_status == {"1": "BUILT"}
        assert snapshot.error is None

    @pytest.mark.asyncio
    async def test_error_card_populates_error(
        self, service: PipelineService, mock_session: AsyncMock
    ) -> None:
        count_result = MagicMock()
        count_result.scalar.return_value = 0

        empty_result = MagicMock()
        empty_result.scalar_one_or_none.return_value = None

        err_result = MagicMock()
        err_card = MagicMock()
        err_card.state_data = {"code": "DEPLOYMENT_FAILED", "message": "boom"}
        err_result.scalar_one_or_none.return_value = err_card

        mock_session.execute.side_effect = [
            count_result,
            count_result,
            count_result,
            count_result,
            empty_result,
            empty_result,
            err_result,
        ]

        voyage = _mock_voyage()
        snapshot = await service.get_status(voyage)
        assert snapshot.error is not None
        assert snapshot.error["code"] == "DEPLOYMENT_FAILED"


class TestReaderFactory:
    def test_reader_instance_has_session_only(self, mock_session: AsyncMock) -> None:
        reader = PipelineService.reader(mock_session)
        assert reader._session is mock_session


class TestPublishFailureIsSwallowed:
    @pytest.mark.asyncio
    async def test_publish_failure_on_start_does_not_raise(
        self,
        service: PipelineService,
        mock_mushi: AsyncMock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        mock_mushi.publish = AsyncMock(side_effect=RuntimeError("redis down"))

        mock_graph = AsyncMock()
        mock_graph.ainvoke = AsyncMock(
            return_value={
                "voyage_id": VOYAGE_ID,
                "user_id": USER_ID,
                "deploy_tier": "preview",
                "max_parallel_shipwrights": 1,
                "task": "t",
                "plan_id": None,
                "poneglyph_count": 0,
                "health_check_count": 0,
                "build_artifact_count": 0,
                "validation_run_id": None,
                "deployment_id": None,
                "error": None,
                "paused": False,
            }
        )
        monkeypatch.setattr(
            "app.services.pipeline_service.build_pipeline_graph",
            lambda _ctx: mock_graph,
        )
        voyage = _mock_voyage()
        # Should not raise
        await service.start(voyage, USER_ID, "task")


class TestPipelineStateShape:
    def test_initial_state_has_all_required_fields(self) -> None:
        from app.crew.pipeline_graph import PipelineState  # noqa: PLC0415

        state: PipelineState = {
            "voyage_id": VOYAGE_ID,
            "user_id": USER_ID,
            "deploy_tier": "preview",
            "max_parallel_shipwrights": 1,
            "task": "t",
            "plan_id": None,
            "poneglyph_count": 0,
            "health_check_count": 0,
            "build_artifact_count": 0,
            "validation_run_id": None,
            "deployment_id": None,
            "error": None,
            "paused": False,
        }
        assert state["voyage_id"] == VOYAGE_ID


_ = Any  # silence unused import warning for typing helper
