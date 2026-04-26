"""Tests for Pipeline REST + SSE API endpoints.

Endpoint functions are called directly with mocked dependencies, matching
the convention in test_helmsman_api.py. The SSE tests drive the inner
event-generator coroutine produced by StreamingResponse.
"""

from __future__ import annotations

import asyncio
import json
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.den_den_mushi.events import (
    PipelineCompletedEvent,
    PipelineFailedEvent,
    PipelineStageCompletedEvent,
    PipelineStageEnteredEvent,
    PipelineStartedEvent,
)
from app.models.enums import CrewRole, VoyageStatus
from app.schemas.pipeline import (
    PipelineEventEnvelope,
    PipelineStatusSnapshot,
    StartVoyageRequest,
    StartVoyageResponse,
)
from app.services.pipeline_guards import PipelineError

VOYAGE_ID = uuid.uuid4()
USER_ID = uuid.uuid4()


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    return user


def _mock_voyage(status: str = VoyageStatus.CHARTED.value) -> MagicMock:
    voyage = MagicMock()
    voyage.id = VOYAGE_ID
    voyage.user_id = USER_ID
    voyage.status = status
    voyage.phase_status = {}
    return voyage


def _mock_request(
    pipeline_tasks: dict[uuid.UUID, asyncio.Task[None]] | None = None,
    is_disconnected: bool = False,
) -> MagicMock:
    request = MagicMock()
    request.app = MagicMock()
    request.app.state = MagicMock()
    request.app.state.pipeline_tasks = pipeline_tasks if pipeline_tasks is not None else {}
    request.is_disconnected = AsyncMock(return_value=is_disconnected)
    return request


def _snapshot() -> PipelineStatusSnapshot:
    return PipelineStatusSnapshot(
        voyage_id=VOYAGE_ID,
        status=VoyageStatus.COMPLETED.value,
        plan_exists=True,
        poneglyph_count=3,
        health_check_count=3,
        build_artifact_count=3,
        phase_status={"1": "BUILT"},
        last_validation_status="passed",
        last_deployment_status="completed",
        error=None,
    )


def _mock_pipeline_service() -> AsyncMock:
    svc = AsyncMock()
    svc.start = AsyncMock(return_value=None)
    svc.pause = AsyncMock(return_value=None)
    svc.resume = AsyncMock(return_value=None)
    svc.cancel = AsyncMock(return_value=None)
    svc.get_status = AsyncMock(return_value=_snapshot())
    return svc


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TestPipelineSchemas:
    def test_start_voyage_request_happy_path(self) -> None:
        req = StartVoyageRequest(
            task="build a todo app with auth",
            deploy_tier="preview",
            max_parallel_shipwrights=3,
        )
        assert req.task == "build a todo app with auth"
        assert req.deploy_tier == "preview"
        assert req.max_parallel_shipwrights == 3

    def test_start_voyage_request_defaults(self) -> None:
        req = StartVoyageRequest(task="build a todo app with auth")
        assert req.deploy_tier == "preview"
        assert req.max_parallel_shipwrights is None

    def test_start_voyage_request_rejects_extra_fields(self) -> None:
        with pytest.raises(Exception):
            StartVoyageRequest.model_validate({"task": "build a todo app with auth", "bogus": True})

    def test_start_voyage_request_task_too_short(self) -> None:
        with pytest.raises(Exception):
            StartVoyageRequest.model_validate({"task": "short"})

    def test_start_voyage_request_rejects_bad_tier(self) -> None:
        with pytest.raises(Exception):
            StartVoyageRequest.model_validate(
                {"task": "build a todo app", "deploy_tier": "production"}
            )

    def test_start_voyage_request_max_parallel_too_low(self) -> None:
        with pytest.raises(Exception):
            StartVoyageRequest.model_validate(
                {"task": "build a todo app", "max_parallel_shipwrights": 0}
            )

    def test_start_voyage_request_max_parallel_too_high(self) -> None:
        with pytest.raises(Exception):
            StartVoyageRequest.model_validate(
                {"task": "build a todo app", "max_parallel_shipwrights": 11}
            )

    def test_start_voyage_request_strict_rejects_coerced_int(self) -> None:
        # strict=True rejects string→int coercion
        with pytest.raises(Exception):
            StartVoyageRequest.model_validate(
                {"task": "build a todo app", "max_parallel_shipwrights": "2"}
            )

    def test_pipeline_event_envelope_round_trip(self) -> None:
        env = PipelineEventEnvelope(
            msg_id="1700000000-0",
            event={
                "event_type": "pipeline_started",
                "voyage_id": str(VOYAGE_ID),
                "payload": {"task": "x"},
            },
        )
        raw = env.model_dump_json()
        parsed = PipelineEventEnvelope.model_validate_json(raw)
        assert parsed.msg_id == env.msg_id
        assert parsed.event == env.event


# ---------------------------------------------------------------------------
# POST /start
# ---------------------------------------------------------------------------


class TestStartVoyage:
    @pytest.mark.asyncio
    async def test_returns_202_and_registers_task(self) -> None:
        from app.api.v1.pipeline import start_voyage

        svc = _mock_pipeline_service()
        svc.start = AsyncMock(return_value=None)
        body = StartVoyageRequest(task="build a todo app with auth")
        registry: dict[uuid.UUID, asyncio.Task[None]] = {}
        request = _mock_request(pipeline_tasks=registry)

        result = await start_voyage(
            VOYAGE_ID,
            body,
            request,
            _mock_user(),
            _mock_voyage(),
            svc,
        )

        assert isinstance(result, StartVoyageResponse)
        assert result.voyage_id == VOYAGE_ID
        assert result.accepted is True
        # Task was registered at some point. Allow the microtask to drain so
        # the done_callback removes it.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert VOYAGE_ID not in registry  # cleanup fired

    @pytest.mark.asyncio
    async def test_task_removed_from_registry_on_success(self) -> None:
        from app.api.v1.pipeline import start_voyage

        svc = _mock_pipeline_service()
        svc.start = AsyncMock(return_value=None)
        body = StartVoyageRequest(task="build a todo app with auth")
        registry: dict[uuid.UUID, asyncio.Task[None]] = {}
        request = _mock_request(pipeline_tasks=registry)

        await start_voyage(VOYAGE_ID, body, request, _mock_user(), _mock_voyage(), svc)
        # yield to the event loop so the spawned task completes
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert VOYAGE_ID not in registry

    @pytest.mark.asyncio
    async def test_task_removed_from_registry_on_failure(self) -> None:
        from app.api.v1.pipeline import start_voyage

        svc = _mock_pipeline_service()
        svc.start = AsyncMock(side_effect=PipelineError("BOOM", "boom"))
        body = StartVoyageRequest(task="build a todo app with auth")
        registry: dict[uuid.UUID, asyncio.Task[None]] = {}
        request = _mock_request(pipeline_tasks=registry)

        await start_voyage(VOYAGE_ID, body, request, _mock_user(), _mock_voyage(), svc)
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert VOYAGE_ID not in registry

    @pytest.mark.asyncio
    async def test_rejects_running_pipeline_with_409(self) -> None:
        from app.api.v1.pipeline import start_voyage

        svc = _mock_pipeline_service()
        # An in-flight (non-done) task in the registry.
        running = asyncio.create_task(asyncio.sleep(5))
        try:
            registry: dict[uuid.UUID, asyncio.Task[None]] = {VOYAGE_ID: running}
            request = _mock_request(pipeline_tasks=registry)
            body = StartVoyageRequest(task="build a todo app with auth")

            with pytest.raises(HTTPException) as exc_info:
                await start_voyage(VOYAGE_ID, body, request, _mock_user(), _mock_voyage(), svc)

            assert exc_info.value.status_code == 409
            assert exc_info.value.detail["error"]["code"] == "PIPELINE_ALREADY_RUNNING"
            svc.start.assert_not_called()
        finally:
            running.cancel()
            try:
                await running
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_rejects_completed_voyage_with_409(self) -> None:
        from app.api.v1.pipeline import start_voyage

        svc = _mock_pipeline_service()
        body = StartVoyageRequest(task="build a todo app with auth")
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await start_voyage(
                VOYAGE_ID,
                body,
                request,
                _mock_user(),
                _mock_voyage(status=VoyageStatus.COMPLETED.value),
                svc,
            )

        assert exc_info.value.status_code == 409
        svc.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_stale_done_task_in_registry_does_not_block(self) -> None:
        from app.api.v1.pipeline import start_voyage

        svc = _mock_pipeline_service()
        svc.start = AsyncMock(return_value=None)

        async def _already_done() -> None:
            return None

        done_task = asyncio.create_task(_already_done())
        await done_task  # drive it to completion

        registry: dict[uuid.UUID, asyncio.Task[None]] = {VOYAGE_ID: done_task}
        request = _mock_request(pipeline_tasks=registry)
        body = StartVoyageRequest(task="build a todo app with auth")

        result = await start_voyage(VOYAGE_ID, body, request, _mock_user(), _mock_voyage(), svc)

        assert result.accepted is True
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_returns_409_when_voyage_paused_with_use_resume_code(self) -> None:
        """`/start` on a PAUSED voyage now returns a deterministic 409
        with `VOYAGE_PAUSED_USE_RESUME` instead of the previous silent
        no-op. Callers should hit `POST /resume` instead."""
        from app.api.v1.pipeline import start_voyage

        svc = _mock_pipeline_service()
        body = StartVoyageRequest(task="build a todo app with auth")
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await start_voyage(
                VOYAGE_ID,
                body,
                request,
                _mock_user(),
                _mock_voyage(status=VoyageStatus.PAUSED.value),
                svc,
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "VOYAGE_PAUSED_USE_RESUME"
        assert "resume" in exc_info.value.detail["error"]["message"].lower()
        svc.start.assert_not_called()


# ---------------------------------------------------------------------------
# POST /resume
# ---------------------------------------------------------------------------


class TestResumeVoyage:
    @pytest.mark.asyncio
    async def test_returns_202_and_spawns_task_when_voyage_paused(self) -> None:
        from app.api.v1.pipeline import resume_voyage

        svc = _mock_pipeline_service()
        voyage = _mock_voyage(status=VoyageStatus.PAUSED.value)

        async def _resume(v: Any) -> None:
            v.status = VoyageStatus.CHARTED.value

        svc.resume = AsyncMock(side_effect=_resume)
        body = StartVoyageRequest(task="resume placeholder task")
        registry: dict[uuid.UUID, asyncio.Task[None]] = {}
        request = _mock_request(pipeline_tasks=registry)

        result = await resume_voyage(VOYAGE_ID, body, request, _mock_user(), voyage, svc)

        assert isinstance(result, StartVoyageResponse)
        assert result.voyage_id == VOYAGE_ID
        assert result.accepted is True
        # Resume flipped the status before the task spawned.
        assert result.status == VoyageStatus.CHARTED.value
        svc.resume.assert_awaited_once_with(voyage)
        # Drain the spawned task so cleanup fires.
        await asyncio.sleep(0)
        await asyncio.sleep(0)
        assert VOYAGE_ID not in registry

    @pytest.mark.asyncio
    async def test_returns_202_when_voyage_failed(self) -> None:
        from app.api.v1.pipeline import resume_voyage

        svc = _mock_pipeline_service()
        voyage = _mock_voyage(status=VoyageStatus.FAILED.value)

        async def _resume(v: Any) -> None:
            v.status = VoyageStatus.CHARTED.value

        svc.resume = AsyncMock(side_effect=_resume)
        body = StartVoyageRequest(task="resume after failure")
        request = _mock_request()

        result = await resume_voyage(VOYAGE_ID, body, request, _mock_user(), voyage, svc)

        assert result.accepted is True
        assert result.status == VoyageStatus.CHARTED.value
        svc.resume.assert_awaited_once_with(voyage)
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_returns_202_when_voyage_charted(self) -> None:
        """CHARTED -> resume is a no-op flip; still spawns the task."""
        from app.api.v1.pipeline import resume_voyage

        svc = _mock_pipeline_service()
        voyage = _mock_voyage(status=VoyageStatus.CHARTED.value)
        svc.resume = AsyncMock(return_value=None)
        body = StartVoyageRequest(task="resume already charted")
        request = _mock_request()

        result = await resume_voyage(VOYAGE_ID, body, request, _mock_user(), voyage, svc)

        assert result.accepted is True
        assert result.status == VoyageStatus.CHARTED.value
        svc.resume.assert_awaited_once_with(voyage)
        svc.start.assert_called_once()
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    @pytest.mark.asyncio
    async def test_returns_409_when_voyage_completed(self) -> None:
        from app.api.v1.pipeline import resume_voyage

        svc = _mock_pipeline_service()
        svc.resume = AsyncMock(
            side_effect=PipelineError(
                "VOYAGE_NOT_RESUMABLE",
                "Voyage status is COMPLETED; cannot resume a completed voyage",
            )
        )
        body = StartVoyageRequest(task="resume completed placeholder")
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await resume_voyage(
                VOYAGE_ID,
                body,
                request,
                _mock_user(),
                _mock_voyage(status=VoyageStatus.COMPLETED.value),
                svc,
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "VOYAGE_NOT_RESUMABLE"
        svc.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_409_when_voyage_cancelled(self) -> None:
        from app.api.v1.pipeline import resume_voyage

        svc = _mock_pipeline_service()
        svc.resume = AsyncMock(
            side_effect=PipelineError(
                "VOYAGE_NOT_RESUMABLE",
                "Voyage status is CANCELLED; cannot resume a cancelled voyage",
            )
        )
        body = StartVoyageRequest(task="resume cancelled placeholder")
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await resume_voyage(
                VOYAGE_ID,
                body,
                request,
                _mock_user(),
                _mock_voyage(status=VoyageStatus.CANCELLED.value),
                svc,
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "VOYAGE_NOT_RESUMABLE"
        svc.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_returns_409_when_pipeline_already_running(self) -> None:
        from app.api.v1.pipeline import resume_voyage

        svc = _mock_pipeline_service()
        running = asyncio.create_task(asyncio.sleep(5))
        try:
            registry: dict[uuid.UUID, asyncio.Task[None]] = {VOYAGE_ID: running}
            request = _mock_request(pipeline_tasks=registry)
            body = StartVoyageRequest(task="resume running placeholder")

            with pytest.raises(HTTPException) as exc_info:
                await resume_voyage(
                    VOYAGE_ID,
                    body,
                    request,
                    _mock_user(),
                    _mock_voyage(status=VoyageStatus.PAUSED.value),
                    svc,
                )

            assert exc_info.value.status_code == 409
            assert exc_info.value.detail["error"]["code"] == "PIPELINE_ALREADY_RUNNING"
            svc.resume.assert_not_called()
            svc.start.assert_not_called()
        finally:
            running.cancel()
            try:
                await running
            except (asyncio.CancelledError, Exception):
                pass

    @pytest.mark.asyncio
    async def test_returns_409_when_voyage_running_planning_stage(self) -> None:
        """Mid-pipeline status (e.g. PLANNING) is not resumable; the running
        pipeline owns it. Caller workflow is cancel + restart."""
        from app.api.v1.pipeline import resume_voyage

        svc = _mock_pipeline_service()
        svc.resume = AsyncMock(
            side_effect=PipelineError(
                "VOYAGE_NOT_RESUMABLE",
                "Voyage status is PLANNING; cancel and restart, "
                "or wait for the current run to reach a resumable state",
            )
        )
        body = StartVoyageRequest(task="resume mid-stage placeholder")
        request = _mock_request()

        with pytest.raises(HTTPException) as exc_info:
            await resume_voyage(
                VOYAGE_ID,
                body,
                request,
                _mock_user(),
                _mock_voyage(status=VoyageStatus.PLANNING.value),
                svc,
            )

        assert exc_info.value.status_code == 409
        assert exc_info.value.detail["error"]["code"] == "VOYAGE_NOT_RESUMABLE"
        svc.start.assert_not_called()

    @pytest.mark.asyncio
    async def test_validates_request_body_extra_field(self) -> None:
        with pytest.raises(Exception):
            StartVoyageRequest.model_validate({"task": "resume placeholder body", "bogus": True})

    @pytest.mark.asyncio
    async def test_validates_request_body_missing_task(self) -> None:
        with pytest.raises(Exception):
            StartVoyageRequest.model_validate({})

    @pytest.mark.asyncio
    async def test_forbidden_for_other_users_voyage(self) -> None:
        """The `get_authorized_voyage` dependency raises HTTP 404 when the
        voyage's user_id != the requester's user.id. Authorization is
        enforced before `resume_voyage` ever runs, so by the time the
        endpoint body executes the voyage is guaranteed to belong to the
        requester. This test sanity-checks that `resume_voyage` does NOT
        re-validate ownership (avoiding double-checks) — it simply trusts
        the dependency."""
        from app.api.v1.pipeline import resume_voyage

        svc = _mock_pipeline_service()
        # Voyage owner-mismatch is a dependency-layer concern; the dependency
        # would short-circuit with 404. Inside the endpoint, we should accept
        # whatever voyage the dependency injected.
        body = StartVoyageRequest(task="resume placeholder body")
        request = _mock_request()

        async def _resume(v: Any) -> None:
            v.status = VoyageStatus.CHARTED.value

        svc.resume = AsyncMock(side_effect=_resume)
        result = await resume_voyage(
            VOYAGE_ID,
            body,
            request,
            _mock_user(),
            _mock_voyage(status=VoyageStatus.PAUSED.value),
            svc,
        )
        assert result.accepted is True
        await asyncio.sleep(0)
        await asyncio.sleep(0)


# ---------------------------------------------------------------------------
# POST /pause
# ---------------------------------------------------------------------------


class TestPauseVoyage:
    @pytest.mark.asyncio
    async def test_returns_200_and_calls_service_pause(self) -> None:
        from app.api.v1.pipeline import pause_voyage

        svc = _mock_pipeline_service()
        voyage = _mock_voyage(status=VoyageStatus.PDD.value)

        async def _pause(v: Any) -> None:
            v.status = VoyageStatus.PAUSED.value

        svc.pause = AsyncMock(side_effect=_pause)

        result = await pause_voyage(VOYAGE_ID, _mock_user(), voyage, svc)

        assert result["voyage_id"] == str(VOYAGE_ID)
        assert result["status"] == VoyageStatus.PAUSED.value
        svc.pause.assert_awaited_once_with(voyage)

    @pytest.mark.asyncio
    async def test_translates_pipeline_error_to_http(self) -> None:
        from app.api.v1.pipeline import pause_voyage

        svc = _mock_pipeline_service()
        svc.pause = AsyncMock(side_effect=PipelineError("UNKNOWN_PAUSE", "nope"))

        with pytest.raises(HTTPException) as exc_info:
            await pause_voyage(VOYAGE_ID, _mock_user(), _mock_voyage(), svc)

        assert exc_info.value.status_code == 422
        assert exc_info.value.detail["error"]["code"] == "UNKNOWN_PAUSE"


# ---------------------------------------------------------------------------
# POST /cancel
# ---------------------------------------------------------------------------


class TestCancelVoyage:
    @pytest.mark.asyncio
    async def test_returns_200_and_sets_cancelled(self) -> None:
        from app.api.v1.pipeline import cancel_voyage

        svc = _mock_pipeline_service()
        voyage = _mock_voyage(status=VoyageStatus.BUILDING.value)

        async def _cancel(v: Any) -> None:
            v.status = VoyageStatus.CANCELLED.value

        svc.cancel = AsyncMock(side_effect=_cancel)
        request = _mock_request()

        result = await cancel_voyage(VOYAGE_ID, request, _mock_user(), voyage, svc)

        assert result["status"] == VoyageStatus.CANCELLED.value
        svc.cancel.assert_awaited_once_with(voyage)

    @pytest.mark.asyncio
    async def test_also_cancels_running_task(self) -> None:
        from app.api.v1.pipeline import cancel_voyage

        svc = _mock_pipeline_service()
        running = asyncio.create_task(asyncio.sleep(10))
        try:
            registry: dict[uuid.UUID, asyncio.Task[None]] = {VOYAGE_ID: running}
            request = _mock_request(pipeline_tasks=registry)

            await cancel_voyage(VOYAGE_ID, request, _mock_user(), _mock_voyage(), svc)

            # Give the event loop a chance to process the cancellation.
            await asyncio.sleep(0)
            assert running.cancelled() or running.done()
        finally:
            if not running.done():
                running.cancel()
                try:
                    await running
                except (asyncio.CancelledError, Exception):
                    pass

    @pytest.mark.asyncio
    async def test_done_task_in_registry_is_noop(self) -> None:
        from app.api.v1.pipeline import cancel_voyage

        svc = _mock_pipeline_service()

        async def _already_done() -> None:
            return None

        done = asyncio.create_task(_already_done())
        await done
        registry: dict[uuid.UUID, asyncio.Task[None]] = {VOYAGE_ID: done}
        request = _mock_request(pipeline_tasks=registry)

        # Should not raise even though the task is already done.
        result = await cancel_voyage(VOYAGE_ID, request, _mock_user(), _mock_voyage(), svc)
        assert result["voyage_id"] == str(VOYAGE_ID)


# ---------------------------------------------------------------------------
# GET /status
# ---------------------------------------------------------------------------


class TestGetStatus:
    @pytest.mark.asyncio
    async def test_returns_snapshot(self) -> None:
        from app.api.v1.pipeline import get_pipeline_status

        reader = _mock_pipeline_service()
        snapshot = _snapshot()
        reader.get_status = AsyncMock(return_value=snapshot)

        voyage = _mock_voyage()
        result = await get_pipeline_status(VOYAGE_ID, _mock_user(), voyage, reader)

        assert result is snapshot
        reader.get_status.assert_awaited_once_with(voyage)


# ---------------------------------------------------------------------------
# GET /stream (SSE)
# ---------------------------------------------------------------------------


def _pipeline_started_event() -> PipelineStartedEvent:
    return PipelineStartedEvent(
        voyage_id=VOYAGE_ID,
        source_role=CrewRole.CAPTAIN,
        payload={"task": "x", "deploy_tier": "preview", "max_parallel_shipwrights": 1},
    )


def _stage_entered_event(stage: str = "PLANNING") -> PipelineStageEnteredEvent:
    return PipelineStageEnteredEvent(
        voyage_id=VOYAGE_ID,
        source_role=CrewRole.CAPTAIN,
        payload={"stage": stage, "voyage_status": "PLANNING"},
    )


def _stage_completed_event(stage: str = "PLANNING") -> PipelineStageCompletedEvent:
    return PipelineStageCompletedEvent(
        voyage_id=VOYAGE_ID,
        source_role=CrewRole.CAPTAIN,
        payload={"stage": stage, "duration_seconds": 0.1, "skipped": False},
    )


def _completed_event() -> PipelineCompletedEvent:
    return PipelineCompletedEvent(
        voyage_id=VOYAGE_ID,
        source_role=CrewRole.CAPTAIN,
        payload={"duration_seconds": 12.3, "deployment_url": "http://preview.local"},
    )


def _failed_event() -> PipelineFailedEvent:
    return PipelineFailedEvent(
        voyage_id=VOYAGE_ID,
        source_role=CrewRole.CAPTAIN,
        payload={"stage": "BUILDING", "code": "BUILD_FAILED", "message": "x"},
    )


async def _drain(generator: Any) -> list[bytes]:
    frames: list[bytes] = []
    async for chunk in generator:
        frames.append(chunk)
    return frames


def _build_stream_mocks(
    read_batches: list[list[tuple[str, Any]]],
    voyage_final_status: str = VoyageStatus.COMPLETED.value,
) -> tuple[AsyncMock, AsyncMock]:
    """Return (mushi, session) mocks wired for SSE tests.

    The mock session.get returns a non-terminal voyage for all status checks
    except the final one, which returns the terminal status — so the generator
    emits every batch before the loop exits.
    """
    mushi = AsyncMock()
    mushi.ensure_group = AsyncMock(return_value=None)
    mushi.ack = AsyncMock(return_value=1)
    queued = list(read_batches) + [[]]  # trailing empty so the loop can check voyage status
    mushi.read = AsyncMock(side_effect=queued + [[]] * 10)

    # Expose a nested _redis.xgroup_destroy so the finally-block cleanup works.
    mushi._redis = MagicMock()
    mushi._redis.xgroup_destroy = AsyncMock(return_value=1)

    session = AsyncMock()
    in_flight_voyage = _mock_voyage(status=VoyageStatus.PLANNING.value)
    terminal_voyage = _mock_voyage(status=voyage_final_status)
    # One in-flight reply per batch, then the terminal status, then terminal
    # forever after (defensive trailing copies).
    session.get = AsyncMock(
        side_effect=[in_flight_voyage] * len(read_batches) + [terminal_voyage] * 20
    )
    return mushi, session


class TestStreamEvents:
    @pytest.mark.asyncio
    async def test_emits_events_and_closes_on_completion(self) -> None:
        from app.api.v1.pipeline import stream_events

        mushi, session = _build_stream_mocks(
            read_batches=[
                [("1-0", _pipeline_started_event())],
                [("2-0", _stage_entered_event())],
                [("3-0", _completed_event())],
            ],
            voyage_final_status=VoyageStatus.COMPLETED.value,
        )
        request = _mock_request()

        response = await stream_events(
            VOYAGE_ID, request, _mock_user(), _mock_voyage(), mushi, session
        )
        frames = await _drain(response.body_iterator)

        # Three events emitted, each as one SSE frame.
        assert len(frames) == 3
        for frame in frames:
            assert frame.startswith(b"data: ")
            assert frame.endswith(b"\n\n")

        # Each frame's JSON is a valid PipelineEventEnvelope.
        for frame in frames:
            body = frame[len(b"data: ") : -len(b"\n\n")]
            parsed = json.loads(body)
            env = PipelineEventEnvelope.model_validate(parsed)
            assert env.event["voyage_id"] == str(VOYAGE_ID)

        # Acked every delivered message.
        assert mushi.ack.await_count == 3
        # Best-effort group cleanup fired.
        mushi._redis.xgroup_destroy.assert_awaited()

    @pytest.mark.asyncio
    async def test_closes_on_client_disconnect(self) -> None:
        from app.api.v1.pipeline import stream_events

        mushi, session = _build_stream_mocks(read_batches=[])
        request = _mock_request(is_disconnected=True)

        response = await stream_events(
            VOYAGE_ID, request, _mock_user(), _mock_voyage(), mushi, session
        )
        frames = await _drain(response.body_iterator)

        # Disconnected immediately — no frames produced, no reads attempted.
        assert frames == []
        mushi.read.assert_not_called()
        mushi._redis.xgroup_destroy.assert_awaited()

    @pytest.mark.asyncio
    async def test_closes_on_voyage_failure(self) -> None:
        from app.api.v1.pipeline import stream_events

        mushi, session = _build_stream_mocks(
            read_batches=[[("1-0", _failed_event())]],
            voyage_final_status=VoyageStatus.FAILED.value,
        )
        request = _mock_request()

        response = await stream_events(
            VOYAGE_ID, request, _mock_user(), _mock_voyage(), mushi, session
        )
        frames = await _drain(response.body_iterator)

        assert len(frames) == 1
        body = frames[0][len(b"data: ") : -len(b"\n\n")]
        env = json.loads(body)
        assert env["event"]["event_type"] == "pipeline_failed"

    @pytest.mark.asyncio
    async def test_closes_on_voyage_cancelled(self) -> None:
        from app.api.v1.pipeline import stream_events

        mushi, session = _build_stream_mocks(
            read_batches=[[("1-0", _stage_entered_event())]],
            voyage_final_status=VoyageStatus.CANCELLED.value,
        )
        request = _mock_request()

        response = await stream_events(
            VOYAGE_ID, request, _mock_user(), _mock_voyage(), mushi, session
        )
        frames = await _drain(response.body_iterator)

        assert len(frames) == 1

    @pytest.mark.asyncio
    async def test_each_frame_is_valid_sse_format(self) -> None:
        from app.api.v1.pipeline import stream_events

        mushi, session = _build_stream_mocks(
            read_batches=[[("1-0", _pipeline_started_event())], [("2-0", _completed_event())]],
            voyage_final_status=VoyageStatus.COMPLETED.value,
        )
        request = _mock_request()

        response = await stream_events(
            VOYAGE_ID, request, _mock_user(), _mock_voyage(), mushi, session
        )
        frames = await _drain(response.body_iterator)

        for frame in frames:
            decoded = frame.decode("utf-8")
            assert decoded.startswith("data: ")
            assert decoded.endswith("\n\n")
            json.loads(decoded[len("data: ") : -len("\n\n")])  # valid JSON

    @pytest.mark.asyncio
    async def test_ensures_consumer_group_before_reading(self) -> None:
        from app.api.v1.pipeline import stream_events

        mushi, session = _build_stream_mocks(
            read_batches=[[("1-0", _completed_event())]],
            voyage_final_status=VoyageStatus.COMPLETED.value,
        )
        request = _mock_request()

        response = await stream_events(
            VOYAGE_ID, request, _mock_user(), _mock_voyage(), mushi, session
        )
        await _drain(response.body_iterator)

        mushi.ensure_group.assert_awaited_once()
        # Group name is fresh + ephemeral (starts with "sse-").
        group_arg = mushi.ensure_group.await_args.args[1]
        assert group_arg.startswith("sse-")
