"""Tests for the Preview REST API (Phase B0) — direct endpoint calls, owner-scoped.

Every endpoint operates on the requesting user's preview for an owner-scoped voyage
(via get_authorized_voyage). Responses carry no secret.
"""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.cabin.backend import ServiceHandle
from app.services.preview_service import PreviewInfo

USER_ID = uuid.uuid4()


def _voyage() -> MagicMock:
    v = MagicMock()
    v.user_id = USER_ID
    v.id = uuid.uuid4()
    return v


def _info() -> PreviewInfo:
    return PreviewInfo(
        preview_id="preview-123",
        url="http://127.0.0.1:3000",
        status="running",
    )


def test_service_handle_url_shape() -> None:
    handle = ServiceHandle(
        service_id="svc-1", url="http://127.0.0.1:3000", port=3000, status="running"
    )
    assert handle.url == "http://127.0.0.1:3000"


class TestStartPreview:
    async def test_starts_and_returns_info(self) -> None:
        from app.api.v1.preview import start_preview

        service = AsyncMock()
        service.start = AsyncMock(return_value=_info())
        session = AsyncMock()
        voyage = _voyage()

        result = await start_preview(voyage=voyage, session=session, service=service)

        assert result.url == "http://127.0.0.1:3000"
        service.start.assert_awaited_once_with(USER_ID, voyage, session, command=None)


class TestGetPreview:
    async def test_returns_status(self) -> None:
        from app.api.v1.preview import get_preview

        service = AsyncMock()
        service.status = AsyncMock(return_value=_info())

        result = await get_preview(voyage=_voyage(), service=service)

        assert result.preview_id == "preview-123"
        service.status.assert_awaited_once_with(USER_ID)

    async def test_404_when_no_preview(self) -> None:
        from app.api.v1.preview import get_preview

        service = AsyncMock()
        service.status = AsyncMock(return_value=None)

        with pytest.raises(HTTPException) as exc:
            await get_preview(voyage=_voyage(), service=service)
        assert exc.value.status_code == 404


class TestPreviewLogs:
    async def test_returns_logs(self) -> None:
        from app.api.v1.preview import get_preview_logs

        service = AsyncMock()
        service.logs = AsyncMock(return_value="line one\nline two\n")

        result = await get_preview_logs(tail=200, voyage=_voyage(), service=service)

        assert result["logs"] == "line one\nline two\n"
        service.logs.assert_awaited_once_with(USER_ID, tail=200)


@pytest.fixture(autouse=True)
def _fast_log_poll(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the SSE poll interval near-zero so stream tests don't sleep for real."""
    import app.api.v1.preview as preview_module

    monkeypatch.setattr(preview_module, "_LOG_POLL_INTERVAL_S", 0.0)


async def _drain(generator: object) -> list[bytes]:
    frames: list[bytes] = []
    async for chunk in generator:  # type: ignore[attr-defined]
        frames.append(chunk)
    return frames


def _stream_request(disconnect_after: int) -> MagicMock:
    """A request whose is_disconnected() returns False then True after N calls."""
    request = MagicMock()
    calls = {"n": 0}

    async def is_disconnected() -> bool:
        calls["n"] += 1
        return calls["n"] > disconnect_after

    request.is_disconnected = is_disconnected
    return request


class TestStreamPreviewLogs:
    async def test_emits_new_log_lines_as_sse_frames(self) -> None:
        from app.api.v1.preview import stream_preview_logs

        service = AsyncMock()
        service.status = AsyncMock(return_value=_info())
        # First poll yields two lines; the second poll has one MORE line appended.
        service.logs = AsyncMock(
            side_effect=["line one\nline two\n", "line one\nline two\nline three\n"]
        )
        request = _stream_request(disconnect_after=2)

        response = await stream_preview_logs(request=request, voyage=_voyage(), service=service)
        frames = await _drain(response.body_iterator)

        # Three lines total across the two polls; only NEW content is emitted.
        assert frames == [
            b"data: line one\n\n",
            b"data: line two\n\n",
            b"data: line three\n\n",
        ]
        service.logs.assert_awaited_with(USER_ID, tail=500)

    async def test_owner_scoped_uses_voyage_owner_id(self) -> None:
        from app.api.v1.preview import stream_preview_logs

        service = AsyncMock()
        service.status = AsyncMock(return_value=_info())
        service.logs = AsyncMock(return_value="hello\n")
        request = _stream_request(disconnect_after=1)

        response = await stream_preview_logs(request=request, voyage=_voyage(), service=service)
        await _drain(response.body_iterator)

        service.status.assert_awaited_with(USER_ID)
        service.logs.assert_awaited_with(USER_ID, tail=500)

    async def test_closes_when_no_preview(self) -> None:
        from app.api.v1.preview import stream_preview_logs

        service = AsyncMock()
        service.status = AsyncMock(return_value=None)
        service.logs = AsyncMock(return_value="")
        request = _stream_request(disconnect_after=5)

        response = await stream_preview_logs(request=request, voyage=_voyage(), service=service)
        frames = await _drain(response.body_iterator)

        assert frames == []
        service.logs.assert_not_awaited()

    async def test_closes_on_client_disconnect(self) -> None:
        from app.api.v1.preview import stream_preview_logs

        service = AsyncMock()
        service.status = AsyncMock(return_value=_info())
        service.logs = AsyncMock(return_value="x\n")
        request = _stream_request(disconnect_after=0)  # disconnected immediately

        response = await stream_preview_logs(request=request, voyage=_voyage(), service=service)
        frames = await _drain(response.body_iterator)

        assert frames == []
        service.logs.assert_not_awaited()


class TestStopPreview:
    async def test_returns_204(self) -> None:
        from app.api.v1.preview import stop_preview

        service = AsyncMock()
        service.stop = AsyncMock()

        result = await stop_preview(voyage=_voyage(), service=service)

        assert result.status_code == 204
        service.stop.assert_awaited_once_with(USER_ID)
