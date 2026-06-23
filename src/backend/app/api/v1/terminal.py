"""Interactive terminal WS endpoint (Phase B3) — a PTY into the user's Cabin.

The final phase of the Live App workstream: a real shell into the user's **Cabin**
(Phase 0b), shown in the deck via ``xterm.js``, bridged over a **bidirectional**
WebSocket. This is the largest attack surface in the epic (interactive arbitrary
execution), so isolation + scoping are paramount — but everything runs INSIDE the
already-isolated gVisor Cabin.

Security posture (see ``deck-cap-B3-terminal.md`` + ``decisions.md``):

- **Owner-scoped, always.** The terminal ONLY ever attaches to the requesting user's
  OWN Cabin: the WS resolves the voyage with the same ``Voyage.user_id == user.id``
  owner check as every deck endpoint and keys the Cabin on the authenticated user's id.
  There is no path to another user's Cabin or shell.
- **Authenticated WS.** Auth rides the ``grandline-bearer`` subprotocol (or the
  ``access_token`` cookie) — never the URL. Bad/missing token → close ``1008``; voyage
  not found / not owned → close ``1003``. We accept-then-close so the browser surfaces
  the code.
- **Arbitrary commands, but ONLY inside the gVisor Cabin.** The PTY runs in the
  persistent per-user container (kernel-filtered syscalls, deny-by-default egress,
  CPU/mem quotas, bounded by the Cabin's hard max lifetime + reaper). No host access.
- **No secret logged.** PTY bytes pass through verbatim and are never logged; the
  session is torn down on disconnect, Cabin destroy, error, or idle timeout.

Wire protocol (bidirectional, mirroring the deck WS envelope):

- server → client: ``{"type": "output", "data": <str>}`` — PTY output.
- client → server: ``{"type": "input", "data": <str>}`` → ``terminal.write``;
  ``{"type": "resize", "cols": <int>, "rows": <int>}`` → ``terminal.resize``.
"""

from __future__ import annotations

import asyncio
import logging
import uuid

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from starlette.websockets import WebSocketState

from app.api.v1.observation_deck import (
    _WS_CLOSE_NORMAL,
    _WS_CLOSE_POLICY_VIOLATION,
    _WS_CLOSE_UNSUPPORTED_DATA,
    _authenticate_ws_token,
    _load_authorized_voyage,
    _ws_credentials,
)
from app.cabin.backend import CabinError, CabinTerminal
from app.core.config import settings
from app.models import async_session
from app.services.cabin_service import CabinService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voyages", tags=["terminal"])

# Custom close code (RFC 6455 4xxx range) for an idle-timed-out terminal session.
_WS_CLOSE_IDLE = 4408


def _get_cabin_service(request: Request | WebSocket) -> CabinService:
    svc: CabinService = request.app.state.cabin_service
    return svc


async def _pump_output(websocket: WebSocket, terminal: CabinTerminal) -> None:
    """PTY output → client. Ends when the PTY closes or the socket drops.

    The raw PTY bytes are decoded leniently and forwarded verbatim — never logged.
    """
    while True:
        chunk = await terminal.read()
        if not chunk:
            return
        if websocket.client_state != WebSocketState.CONNECTED:
            return
        try:
            await websocket.send_json({"type": "output", "data": chunk.decode(errors="replace")})
        except (WebSocketDisconnect, RuntimeError):
            return


async def _pump_input(websocket: WebSocket, terminal: CabinTerminal) -> None:
    """Client frames → PTY. Handles input + resize; ignores malformed frames.

    Frame contents are NEVER logged (they may carry a secret typed by the user).
    """
    while True:
        try:
            frame = await websocket.receive_json()
        except (WebSocketDisconnect, RuntimeError):
            return
        if not isinstance(frame, dict):
            continue
        kind = frame.get("type")
        if kind == "input":
            data = frame.get("data")
            if isinstance(data, str):
                await terminal.write(data.encode())
        elif kind == "resize":
            cols = frame.get("cols")
            rows = frame.get("rows")
            if isinstance(cols, int) and isinstance(rows, int):
                await terminal.resize(cols, rows)
        # Unknown frame types are ignored — the session stays up.


@router.websocket("/{voyage_id}/terminal")
async def voyage_terminal(
    websocket: WebSocket,
    voyage_id: uuid.UUID,
) -> None:
    """Bidirectional PTY WS into the voyage owner's Cabin (Phase B3).

    Auth: ``Sec-WebSocket-Protocol: grandline-bearer, <jwt>`` (preferred) or the
    ``access_token`` cookie. The token is never read from the URL.

    Close-code semantics:
      - ``1008`` policy violation → auth failed (missing/invalid/expired token) OR the
        terminal feature is disabled.
      - ``1003`` unsupported data → voyage not found / not owned.
      - ``4408`` → idle timeout (no I/O within ``terminal_idle_timeout_seconds``).
      - ``1000`` normal → PTY ended / client disconnect / clean teardown.
    """
    token, accept_protocol = _ws_credentials(websocket)

    # Auth + ownership are resolved BEFORE accept(): on policy/unsupported closes we
    # accept-then-close (so the browser surfaces our code) but never bridge a PTY.
    async with async_session() as session:
        if not settings.terminal_enabled:
            await websocket.accept(subprotocol=accept_protocol)
            await websocket.close(code=_WS_CLOSE_POLICY_VIOLATION)
            return

        user = await _authenticate_ws_token(token, session) if token else None
        if user is None:
            await websocket.accept(subprotocol=accept_protocol)
            await websocket.close(code=_WS_CLOSE_POLICY_VIOLATION)
            return

        # Owner-scope: the voyage MUST belong to the authenticated user. The Cabin is
        # then keyed on that same user's id — no path to another user's shell.
        voyage = await _load_authorized_voyage(session, voyage_id, user)
        if voyage is None:
            await websocket.accept(subprotocol=accept_protocol)
            await websocket.close(code=_WS_CLOSE_UNSUPPORTED_DATA)
            return

        cabin_service = _get_cabin_service(websocket)
        try:
            terminal = await cabin_service.open_terminal(user.id, session)
        except CabinError:
            # Cabin/backend unavailable — never leak details to the client.
            await websocket.accept(subprotocol=accept_protocol)
            await websocket.close(code=_WS_CLOSE_UNSUPPORTED_DATA)
            return

    await websocket.accept(subprotocol=accept_protocol)

    idle_timeout = settings.terminal_idle_timeout_seconds
    output_task = asyncio.create_task(_pump_output(websocket, terminal))
    input_task = asyncio.create_task(_pump_input(websocket, terminal))
    close_code = _WS_CLOSE_NORMAL
    try:
        # The two pumps race; whichever finishes first ends the session. An idle
        # window with no I/O on either side tears the session down (no orphans).
        done, pending = await asyncio.wait(
            {output_task, input_task},
            timeout=idle_timeout if idle_timeout > 0 else None,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if not done:
            close_code = _WS_CLOSE_IDLE
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("Unexpected error in voyage_terminal for voyage %s", voyage_id)
    finally:
        for task in (output_task, input_task):
            if not task.done():
                task.cancel()
        await asyncio.gather(output_task, input_task, return_exceptions=True)
        await terminal.close()
        if websocket.client_state == WebSocketState.CONNECTED:
            try:
                await websocket.close(code=close_code)
            except RuntimeError:  # pragma: no cover - already closed
                pass
