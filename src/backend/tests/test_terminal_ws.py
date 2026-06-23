"""Tests for the bidirectional terminal WS endpoint (Phase B3).

Covers the security gates (auth-fail → 1008, owner-scope fail → 1003), the
bidirectional bridge (an input frame reaches ``terminal.write``; PTY output reaches
the client), resize forwarding, and clean teardown. The handler is invoked directly
with a mocked starlette WebSocket + a real Null terminal + patched module-level
helpers, mirroring ``test_observation_deck_ws.py``.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.websockets import WebSocketDisconnect, WebSocketState

from app.api.v1 import terminal as terminal_mod
from app.api.v1.terminal import voyage_terminal
from app.cabin.null_backend import _NullCabinTerminal
from app.models.enums import VoyageStatus
from app.models.voyage import Voyage

USER_ID = uuid.uuid4()
VOYAGE_ID = uuid.uuid4()
TOKEN = "test-token"

_NORMAL = 1000
_UNSUPPORTED = 1003
_POLICY = 1008
_IDLE = 4408


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


def _mock_websocket(
    *,
    token: str | None = TOKEN,
    inbound: list[Any] | None = None,
) -> MagicMock:
    """A WebSocket double that records accept/close/send_json + replays inbound frames.

    ``inbound`` is the queue of frames ``receive_json`` returns; once drained it raises
    ``WebSocketDisconnect`` to end the input pump (mimicking a client disconnect).
    """
    ws = MagicMock()
    ws.client_state = WebSocketState.CONNECTING
    ws.headers = (
        {"sec-websocket-protocol": f"grandline-bearer, {token}"} if token is not None else {}
    )
    ws.cookies = {}

    async def _accept(subprotocol: str | None = None) -> None:
        ws.client_state = WebSocketState.CONNECTED
        ws._accepted_subprotocol = subprotocol

    async def _close(code: int = 1000, reason: str | None = None) -> None:
        ws.client_state = WebSocketState.DISCONNECTED
        ws._closed_with = (code, reason)

    async def _send_json(frame: dict[str, Any]) -> None:
        ws._sent_frames.append(frame)

    frames = list(inbound or [])

    async def _receive_json() -> Any:
        if frames:
            return frames.pop(0)
        raise WebSocketDisconnect(code=1000)

    ws._sent_frames = []
    ws._closed_with = None
    ws._accepted_subprotocol = None
    ws.accept = AsyncMock(side_effect=_accept)
    ws.close = AsyncMock(side_effect=_close)
    ws.send_json = AsyncMock(side_effect=_send_json)
    ws.receive_json = AsyncMock(side_effect=_receive_json)
    ws.app = MagicMock()
    ws.app.state = MagicMock()
    return ws


def _patch_handshake(
    monkeypatch: pytest.MonkeyPatch,
    *,
    user: Any,
    voyage: Any,
) -> None:
    monkeypatch.setattr(terminal_mod, "_authenticate_ws_token", AsyncMock(return_value=user))
    monkeypatch.setattr(terminal_mod, "_load_authorized_voyage", AsyncMock(return_value=voyage))

    session = AsyncMock()

    def _factory() -> Any:
        ctx = AsyncMock()
        ctx.__aenter__ = AsyncMock(return_value=session)
        ctx.__aexit__ = AsyncMock(return_value=None)
        return ctx

    monkeypatch.setattr(terminal_mod, "async_session", _factory)


def _wire_cabin(ws: MagicMock, terminal: Any) -> AsyncMock:
    cabin_service = AsyncMock()
    cabin_service.open_terminal = AsyncMock(return_value=terminal)
    ws.app.state.cabin_service = cabin_service
    return cabin_service


@pytest.fixture(autouse=True)
def _enable_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    # Default-on for the bridge tests; a short idle timeout keeps tests fast.
    monkeypatch.setattr(terminal_mod.settings, "terminal_enabled", True)
    monkeypatch.setattr(terminal_mod.settings, "terminal_idle_timeout_seconds", 5)


# ---------------------------------------------------------------------------
# Security gates
# ---------------------------------------------------------------------------


class TestTerminalAuth:
    @pytest.mark.asyncio
    async def test_invalid_token_closes_with_1008(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_handshake(monkeypatch, user=None, voyage=None)
        ws = _mock_websocket(token="bad-token")

        await voyage_terminal(ws, VOYAGE_ID)

        ws.close.assert_awaited()
        assert ws._closed_with[0] == _POLICY
        # The bearer subprotocol is echoed even on the failure close.
        assert ws._accepted_subprotocol == "grandline-bearer"

    @pytest.mark.asyncio
    async def test_missing_credentials_close_with_1008(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        auth = AsyncMock(return_value=_mock_user())
        monkeypatch.setattr(terminal_mod, "_authenticate_ws_token", auth)
        ws = _mock_websocket(token=None)

        await voyage_terminal(ws, VOYAGE_ID)

        auth.assert_not_awaited()
        assert ws._closed_with[0] == _POLICY

    @pytest.mark.asyncio
    async def test_disabled_feature_closes_with_1008(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(terminal_mod.settings, "terminal_enabled", False)
        auth = AsyncMock(return_value=_mock_user())
        monkeypatch.setattr(terminal_mod, "_authenticate_ws_token", auth)
        ws = _mock_websocket(token=TOKEN)

        await voyage_terminal(ws, VOYAGE_ID)

        # Feature gate trips before authentication.
        auth.assert_not_awaited()
        assert ws._closed_with[0] == _POLICY

    @pytest.mark.asyncio
    async def test_unowned_voyage_closes_with_1003(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # Authenticated, but the voyage is not owned → 1003 (never opens a terminal).
        _patch_handshake(monkeypatch, user=_mock_user(), voyage=None)
        ws = _mock_websocket(token=TOKEN)
        cabin = _wire_cabin(ws, _NullCabinTerminal())

        await voyage_terminal(ws, VOYAGE_ID)

        cabin.open_terminal.assert_not_awaited()
        assert ws._closed_with[0] == _UNSUPPORTED


# ---------------------------------------------------------------------------
# Bidirectional bridge
# ---------------------------------------------------------------------------


class TestTerminalBridge:
    @pytest.mark.asyncio
    async def test_input_frame_reaches_terminal_and_output_reaches_client(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _patch_handshake(monkeypatch, user=_mock_user(), voyage=_mock_voyage())
        terminal = _NullCabinTerminal()
        ws = _mock_websocket(
            token=TOKEN,
            inbound=[{"type": "input", "data": "whoami\n"}],
        )
        _wire_cabin(ws, terminal)

        await voyage_terminal(ws, VOYAGE_ID)

        # The Null terminal echoes input back as output; the canned prompt + the echo
        # should both have been forwarded to the client as "output" frames.
        outputs = [f["data"] for f in ws._sent_frames if f["type"] == "output"]
        assert any("whoami" in o for o in outputs)
        # The terminal was opened owner-scoped on the authenticated user's id.
        ws.app.state.cabin_service.open_terminal.assert_awaited_once()
        args, _ = ws.app.state.cabin_service.open_terminal.call_args
        assert args[0] == USER_ID

    @pytest.mark.asyncio
    async def test_resize_frame_is_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_handshake(monkeypatch, user=_mock_user(), voyage=_mock_voyage())
        terminal = MagicMock()
        terminal.read = AsyncMock(side_effect=[b"prompt$ ", b""])
        terminal.write = AsyncMock()
        terminal.resize = AsyncMock()
        terminal.close = AsyncMock()
        ws = _mock_websocket(
            token=TOKEN,
            inbound=[{"type": "resize", "cols": 132, "rows": 43}],
        )
        _wire_cabin(ws, terminal)

        await voyage_terminal(ws, VOYAGE_ID)

        terminal.resize.assert_awaited_with(132, 43)

    @pytest.mark.asyncio
    async def test_malformed_frame_is_ignored(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_handshake(monkeypatch, user=_mock_user(), voyage=_mock_voyage())
        terminal = MagicMock()
        terminal.read = AsyncMock(side_effect=[b"prompt$ ", b""])
        terminal.write = AsyncMock()
        terminal.resize = AsyncMock()
        terminal.close = AsyncMock()
        # A bad-type frame then an unknown-type frame — neither should crash the bridge.
        ws = _mock_websocket(
            token=TOKEN,
            inbound=["not-a-dict", {"type": "bogus"}],
        )
        _wire_cabin(ws, terminal)

        await voyage_terminal(ws, VOYAGE_ID)

        terminal.write.assert_not_awaited()
        terminal.resize.assert_not_awaited()
        # Clean teardown still happened.
        terminal.close.assert_awaited()

    @pytest.mark.asyncio
    async def test_clean_teardown_on_disconnect(self, monkeypatch: pytest.MonkeyPatch) -> None:
        _patch_handshake(monkeypatch, user=_mock_user(), voyage=_mock_voyage())
        terminal = MagicMock()
        terminal.read = AsyncMock(side_effect=[b"prompt$ ", b""])
        terminal.write = AsyncMock()
        terminal.resize = AsyncMock()
        terminal.close = AsyncMock()
        ws = _mock_websocket(token=TOKEN, inbound=[])  # disconnect immediately
        _wire_cabin(ws, terminal)

        await voyage_terminal(ws, VOYAGE_ID)

        terminal.close.assert_awaited_once()
        assert ws._closed_with[0] == _NORMAL

    @pytest.mark.asyncio
    async def test_cabin_unavailable_closes_with_1003(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from app.cabin.backend import CabinError

        _patch_handshake(monkeypatch, user=_mock_user(), voyage=_mock_voyage())
        ws = _mock_websocket(token=TOKEN)
        cabin_service = AsyncMock()
        cabin_service.open_terminal = AsyncMock(
            side_effect=CabinError("BACKEND_UNAVAILABLE", "no docker")
        )
        ws.app.state.cabin_service = cabin_service

        await voyage_terminal(ws, VOYAGE_ID)

        assert ws._closed_with[0] == _UNSUPPORTED
