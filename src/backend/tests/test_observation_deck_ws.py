"""Tests for the Observation Deck WS endpoint (Phase 16.0).

Covers P1 (transport), P4 (auth-fail close), P10 (terminal-state close).
The endpoint handler is invoked directly with a mocked starlette WebSocket
+ patched module-level helpers, mirroring test_pipeline_api.py's pattern
for the SSE endpoint.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from starlette.websockets import WebSocketState

from app.api.v1.observation_deck import voyage_event_stream
from app.den_den_mushi.events import PipelineCompletedEvent, PipelineStartedEvent
from app.models.enums import CrewRole, VoyageStatus
from app.models.voyage import Voyage

USER_ID = uuid.uuid4()
VOYAGE_ID = uuid.uuid4()
TOKEN = "test-token"

_TERMINAL_NORMAL = 1000
_UNSUPPORTED = 1003
_POLICY = 1008


def _mock_user() -> MagicMock:
    user = MagicMock()
    user.id = USER_ID
    user.is_active = True
    return user


def _mock_voyage(status_: str = VoyageStatus.PDD.value) -> Voyage:
    v = Voyage()
    v.id = VOYAGE_ID
    v.user_id = USER_ID
    v.title = "x"
    v.status = status_
    v.phase_status = {}
    return v


def _mock_websocket(initial_state: WebSocketState = WebSocketState.CONNECTING) -> MagicMock:
    """A WebSocket double that records accept/close/send_json calls."""
    ws = MagicMock()
    ws.client_state = initial_state

    async def _accept() -> None:
        ws.client_state = WebSocketState.CONNECTED

    async def _close(code: int = 1000, reason: str | None = None) -> None:
        ws.client_state = WebSocketState.DISCONNECTED
        ws._closed_with = (code, reason)

    async def _send_json(frame: dict[str, Any]) -> None:
        ws._sent_frames.append(frame)

    ws._sent_frames = []
    ws._closed_with = None
    ws.accept = AsyncMock(side_effect=_accept)
    ws.close = AsyncMock(side_effect=_close)
    ws.send_json = AsyncMock(side_effect=_send_json)
    ws.app = MagicMock()
    ws.app.state = MagicMock()
    return ws


def _make_started_event() -> PipelineStartedEvent:
    return PipelineStartedEvent(
        voyage_id=VOYAGE_ID,
        source_role=CrewRole.CAPTAIN,
        payload={"task": "x", "deploy_tier": "preview", "max_parallel_shipwrights": 1},
    )


def _make_completed_event() -> PipelineCompletedEvent:
    return PipelineCompletedEvent(
        voyage_id=VOYAGE_ID,
        source_role=CrewRole.CAPTAIN,
        payload={"duration_seconds": 1.0, "deployment_url": None},
    )


def _patch_session_factory(
    monkeypatch: pytest.MonkeyPatch,
    *,
    handshake_user: Any,
    handshake_voyage: Any,
    later_voyage: Any | None = None,
) -> None:
    """Patch the module-level helpers + async_session for WS tests.

    The endpoint relies on three module-level seams:
      1. `_authenticate_ws_token(token, session)` → User | None.
      2. `_load_authorized_voyage(session, voyage_id, user)` → Voyage | None.
      3. `async_session()` context manager — used to re-fetch voyage status
         on each loop iteration via `session.get(Voyage, id, populate_existing=True)`.

    Patching the helpers directly is far simpler than reproducing the SQL
    side-effect chain.
    """
    later = later_voyage if later_voyage is not None else handshake_voyage

    monkeypatch.setattr(
        "app.api.v1.observation_deck._authenticate_ws_token",
        AsyncMock(return_value=handshake_user),
    )
    monkeypatch.setattr(
        "app.api.v1.observation_deck._load_authorized_voyage",
        AsyncMock(return_value=handshake_voyage),
    )

    later_session = AsyncMock()
    later_session.get = AsyncMock(return_value=later)

    def _factory() -> Any:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=later_session)
        ctx.__aexit__ = AsyncMock(return_value=None)
        return ctx

    monkeypatch.setattr("app.api.v1.observation_deck.async_session", _factory)


def _build_mushi(read_batches: list[list[tuple[str, Any]]]) -> AsyncMock:
    mushi = AsyncMock()
    mushi.ensure_group = AsyncMock(return_value=None)
    mushi.ack = AsyncMock(return_value=1)
    mushi.read = AsyncMock(side_effect=list(read_batches) + [[]] * 10)
    mushi._redis = MagicMock()
    mushi._redis.xgroup_destroy = AsyncMock(return_value=1)
    return mushi


# ---------------------------------------------------------------------------
# Auth + authorization (P4)
# ---------------------------------------------------------------------------


class TestWsAuth:
    @pytest.mark.asyncio
    async def test_invalid_token_closes_with_1008(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # No user returned for token → auth fails.
        _patch_session_factory(monkeypatch, handshake_user=None, handshake_voyage=None)
        ws = _mock_websocket()
        ws.app.state.den_den_mushi = AsyncMock()

        await voyage_event_stream(ws, VOYAGE_ID, token="bad-token")

        ws.accept.assert_awaited_once()
        ws.close.assert_awaited_once()
        assert ws._closed_with[0] == _POLICY

    @pytest.mark.asyncio
    async def test_voyage_not_found_closes_with_1003(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_session_factory(monkeypatch, handshake_user=_mock_user(), handshake_voyage=None)
        ws = _mock_websocket()
        ws.app.state.den_den_mushi = AsyncMock()

        await voyage_event_stream(ws, VOYAGE_ID, token=TOKEN)

        ws.close.assert_awaited_once()
        assert ws._closed_with[0] == _UNSUPPORTED


# ---------------------------------------------------------------------------
# Forwarding + terminal closure (P10)
# ---------------------------------------------------------------------------


class TestWsForwarding:
    @pytest.mark.asyncio
    async def test_forwards_event_then_closes_on_terminal(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Active voyage at handshake; flips terminal on the live status check.
        active = _mock_voyage(status_=VoyageStatus.PDD.value)
        terminal = _mock_voyage(status_=VoyageStatus.COMPLETED.value)
        _patch_session_factory(
            monkeypatch,
            handshake_user=_mock_user(),
            handshake_voyage=active,
            later_voyage=terminal,
        )

        mushi = _build_mushi([[("1-0", _make_started_event())]])
        ws = _mock_websocket()
        ws.app.state.den_den_mushi = mushi

        await voyage_event_stream(ws, VOYAGE_ID, token=TOKEN)

        # One forwarded event in the canonical envelope shape.
        assert len(ws._sent_frames) == 1
        frame = ws._sent_frames[0]
        assert frame["type"] == "event"
        assert frame["payload"]["msg_id"] == "1-0"
        assert frame["payload"]["event"]["event_type"] == "pipeline_started"

        # Acknowledged delivery; closed with 1000 + reason "voyage-terminal" (P10).
        mushi.ack.assert_awaited()
        ws.close.assert_awaited()
        assert ws._closed_with[0] == _TERMINAL_NORMAL
        assert ws._closed_with[1] == "voyage-terminal"

        # Best-effort group cleanup ran.
        mushi._redis.xgroup_destroy.assert_awaited()

    @pytest.mark.asyncio
    async def test_already_terminal_at_connect_closes_after_replay(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        terminal = _mock_voyage(status_=VoyageStatus.COMPLETED.value)
        _patch_session_factory(monkeypatch, handshake_user=_mock_user(), handshake_voyage=terminal)
        mushi = _build_mushi([[("1-0", _make_completed_event())]])
        ws = _mock_websocket()
        ws.app.state.den_den_mushi = mushi

        await voyage_event_stream(ws, VOYAGE_ID, token=TOKEN)

        assert len(ws._sent_frames) == 1
        assert ws._closed_with[0] == _TERMINAL_NORMAL
        assert ws._closed_with[1] == "voyage-terminal"

    @pytest.mark.asyncio
    async def test_forwarded_frame_envelope_shape(self, monkeypatch: pytest.MonkeyPatch) -> None:
        active = _mock_voyage(status_=VoyageStatus.PDD.value)
        terminal = _mock_voyage(status_=VoyageStatus.COMPLETED.value)
        _patch_session_factory(
            monkeypatch,
            handshake_user=_mock_user(),
            handshake_voyage=active,
            later_voyage=terminal,
        )

        mushi = _build_mushi([[("17-3", _make_started_event())]])
        ws = _mock_websocket()
        ws.app.state.den_den_mushi = mushi

        await voyage_event_stream(ws, VOYAGE_ID, token=TOKEN)

        frame = ws._sent_frames[0]
        # Forward-compatible envelope: {"type": "event", "payload": {...}}
        # so Phase 17 can add upstream {"type": "intervention", ...} later.
        assert set(frame.keys()) == {"type", "payload"}
        assert set(frame["payload"].keys()) == {"msg_id", "event"}

    @pytest.mark.asyncio
    async def test_cleanup_runs_on_unexpected_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        active = _mock_voyage(status_=VoyageStatus.PDD.value)
        _patch_session_factory(monkeypatch, handshake_user=_mock_user(), handshake_voyage=active)

        mushi = AsyncMock()
        mushi.ensure_group = AsyncMock(side_effect=RuntimeError("redis down"))
        mushi._redis = MagicMock()
        mushi._redis.xgroup_destroy = AsyncMock(return_value=1)
        ws = _mock_websocket()
        ws.app.state.den_den_mushi = mushi

        # Should not raise — the unexpected error is logged and the finally
        # block still runs.
        await voyage_event_stream(ws, VOYAGE_ID, token=TOKEN)

        mushi._redis.xgroup_destroy.assert_awaited()


# Imports above retained for clarity even if not all used yet.
_ = patch
