"""Observation Deck REST + WS endpoints.

Phase 16.0. Implements:
- ``GET /api/v1/voyages`` — paginated voyage list (P7).
- ``GET /api/v1/voyages/{voyage_id}/crew-actions`` — paginated log (P6).
- ``WS  /api/v1/voyages/{voyage_id}/events`` — live event stream (P1, P10, P4).
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
    WebSocket,
    WebSocketDisconnect,
    status,
)
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.websockets import WebSocketState

from app.api.v1._cursor import CursorError, decode_cursor, encode_cursor
from app.api.v1.dependencies import (
    get_authorized_voyage,
    get_current_user,
)
from app.core.security import JWTError, decode_token
from app.den_den_mushi.constants import stream_key
from app.den_den_mushi.mushi import DenDenMushi
from app.models import async_session, get_db
from app.models.crew_action import CrewAction
from app.models.enums import VoyageStatus
from app.models.user import User
from app.models.voyage import Voyage
from app.schemas.observation_deck import (
    CrewActionListResponse,
    CrewActionRead,
    VoyageListItem,
    VoyageListResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/voyages", tags=["observation-deck"])

_TERMINAL_STATUSES = frozenset(
    {
        VoyageStatus.COMPLETED.value,
        VoyageStatus.FAILED.value,
        VoyageStatus.CANCELLED.value,
    }
)
_TERMINAL_REASON = "voyage-terminal"
_WS_BLOCK_MS = 1000

# WebSocket close codes (RFC 6455 + custom).
_WS_CLOSE_NORMAL = 1000
_WS_CLOSE_UNSUPPORTED_DATA = 1003
_WS_CLOSE_POLICY_VIOLATION = 1008


# ------------------------- REST: /voyages list ------------------------------


@router.get("", response_model=VoyageListResponse)
async def list_voyages(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    voyage_status: Literal["active", "terminal"] | None = Query(default=None, alias="status"),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> VoyageListResponse:
    """List the caller's voyages, sorted by ``(updated_at DESC, id DESC)`` (P7).

    Cursor pagination on ``(updated_at, id)``. ``status="active"`` excludes
    COMPLETED/CANCELLED/FAILED; ``status="terminal"`` is only those.
    """
    stmt = select(Voyage).where(Voyage.user_id == user.id)

    if voyage_status == "active":
        stmt = stmt.where(Voyage.status.notin_(_TERMINAL_STATUSES))
    elif voyage_status == "terminal":
        stmt = stmt.where(Voyage.status.in_(_TERMINAL_STATUSES))

    if cursor is not None:
        try:
            decoded = decode_cursor(cursor)
        except CursorError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "INVALID_CURSOR", "message": str(exc)}},
            ) from exc
        # (updated_at, id) < (cursor.ts, cursor.id) expanded to a portable
        # disjunction so we don't depend on dialect row-tuple support.
        stmt = stmt.where(
            or_(
                Voyage.updated_at < decoded.ts,
                and_(
                    Voyage.updated_at == decoded.ts,
                    Voyage.id < decoded.id,
                ),
            )
        )

    stmt = stmt.order_by(Voyage.updated_at.desc(), Voyage.id.desc()).limit(limit)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    next_cursor: str | None = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = encode_cursor(last.updated_at, last.id)

    items = [VoyageListItem.model_validate(v) for v in rows]
    return VoyageListResponse(items=items, next_cursor=next_cursor)


# --------------- REST: /voyages/{voyage_id}/crew-actions --------------------


@router.get("/{voyage_id}/crew-actions", response_model=CrewActionListResponse)
async def list_crew_actions(
    voyage_id: uuid.UUID,
    voyage: Voyage = Depends(get_authorized_voyage),
    session: AsyncSession = Depends(get_db),
    cursor: str | None = Query(default=None),
    limit: int = Query(default=200, ge=1, le=1000),
) -> CrewActionListResponse:
    """Paginated CrewAction log for a voyage, sorted by ``(created_at, id) DESC``.

    Cursor encodes ``(created_at, id)`` (P6). ``CrewActionRead.details``
    carries ``details.event_id`` so the frontend can dedupe a live
    ``crew_action_recorded`` WS event against the row (P3 correlation).
    """
    stmt = select(CrewAction).where(CrewAction.voyage_id == voyage.id)

    if cursor is not None:
        try:
            decoded = decode_cursor(cursor)
        except CursorError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={"error": {"code": "INVALID_CURSOR", "message": str(exc)}},
            ) from exc
        # Use explicit (a, b) < (c, d) ↔ a < c OR (a = c AND b < d) so the
        # comparison works on dialects without row-tuple operators.
        stmt = stmt.where(
            or_(
                CrewAction.created_at < decoded.ts,
                and_(
                    CrewAction.created_at == decoded.ts,
                    CrewAction.id < decoded.id,
                ),
            )
        )

    stmt = stmt.order_by(CrewAction.created_at.desc(), CrewAction.id.desc()).limit(limit)

    result = await session.execute(stmt)
    rows = list(result.scalars().all())

    next_cursor: str | None = None
    if len(rows) == limit:
        last = rows[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    items = [CrewActionRead.model_validate(a) for a in rows]
    return CrewActionListResponse(items=items, next_cursor=next_cursor)


# ----------------------- WS: /voyages/{voyage_id}/events --------------------

# Clients authenticate the WS handshake via the subprotocol list:
#   new WebSocket(url, ["grandline-bearer", <jwt>])
# The token never appears in the URL (proxy logs, browser history). Same-origin
# deployments may instead rely on the access_token cookie, which browsers
# attach to the handshake automatically.
_WS_BEARER_PROTOCOL = "grandline-bearer"


def _ws_credentials(websocket: WebSocket) -> tuple[str | None, str | None]:
    """Extract ``(token, subprotocol_to_echo)`` from the WS handshake.

    When the client offers the bearer subprotocol we must echo it back on
    accept() (browsers fail the connection if the server selects none), so the
    accept subprotocol is returned alongside the token.
    """
    header = websocket.headers.get("sec-websocket-protocol", "")
    offered = [p.strip() for p in header.split(",") if p.strip()]
    if _WS_BEARER_PROTOCOL in offered:
        token = next((p for p in offered if p != _WS_BEARER_PROTOCOL), None)
        return token, _WS_BEARER_PROTOCOL
    return websocket.cookies.get("access_token"), None


async def _authenticate_ws_token(token: str, session: AsyncSession) -> User | None:
    """Mirror `get_current_user` for the WS handshake path.

    Returns the user on success, ``None`` on any auth failure.
    """
    try:
        payload = decode_token(token)
    except JWTError:
        return None

    if payload.get("type") != "access":
        return None

    sub = payload.get("sub")
    if not sub:
        return None

    try:
        user_id = uuid.UUID(sub)
    except (TypeError, ValueError):
        return None

    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    return user


async def _load_authorized_voyage(
    session: AsyncSession,
    voyage_id: uuid.UUID,
    user: User,
) -> Voyage | None:
    result = await session.execute(
        select(Voyage).where(Voyage.id == voyage_id, Voyage.user_id == user.id)
    )
    return result.scalar_one_or_none()


@router.websocket("/{voyage_id}/events")
async def voyage_event_stream(
    websocket: WebSocket,
    voyage_id: uuid.UUID,
) -> None:
    """Live WS event stream (P1/P4/P10).

    Auth: ``Sec-WebSocket-Protocol: grandline-bearer, <jwt>`` (preferred) or
    the ``access_token`` cookie. The token is never read from the URL.

    Close-code semantics:
      - ``1008`` policy violation → auth failed (missing/invalid/expired token).
      - ``1003`` unsupported data → voyage not found / not owned.
      - ``1000`` normal + reason ``"voyage-terminal"`` → voyage flipped terminal.
      - normal close (no code, no reason) → client disconnect.

    Forwards each Redis stream message as a JSON text frame::

        {"type": "event", "payload": {"msg_id": str, "event": <model_dump>}}

    Forward-compatible envelope so Phase 17 can add upstream message
    types (e.g. ``{"type": "intervention", ...}``) later.
    """
    mushi: DenDenMushi = websocket.app.state.den_den_mushi
    token, accept_protocol = _ws_credentials(websocket)

    # Auth + voyage check happen before accept(): on policy/unsupported
    # closes we *don't* upgrade — we close with the appropriate code.
    async with async_session() as session:
        user = await _authenticate_ws_token(token, session) if token else None
        if user is None:
            # Per RFC 6455 starlette must accept before close-with-code so
            # the close frame actually reaches the client.
            await websocket.accept(subprotocol=accept_protocol)
            await websocket.close(code=_WS_CLOSE_POLICY_VIOLATION)
            return

        voyage = await _load_authorized_voyage(session, voyage_id, user)
        if voyage is None:
            await websocket.accept(subprotocol=accept_protocol)
            await websocket.close(code=_WS_CLOSE_UNSUPPORTED_DATA)
            return

        # Snapshot terminal-state at connect time so tests can observe
        # "already terminal" close.
        initial_terminal = voyage.status in _TERMINAL_STATUSES

    await websocket.accept(subprotocol=accept_protocol)

    stream = stream_key(voyage_id)
    group = f"sse-{uuid.uuid4().hex}"
    consumer = f"sse-{uuid.uuid4().hex[:8]}"

    try:
        await mushi.ensure_group(stream, group)

        while True:
            if websocket.client_state != WebSocketState.CONNECTED:
                return

            batch = await mushi.read(
                stream=stream,
                group=group,
                consumer=consumer,
                count=10,
                block_ms=_WS_BLOCK_MS,
            )
            for msg_id, event in batch:
                frame = {
                    "type": "event",
                    "payload": {
                        "msg_id": msg_id,
                        "event": event.model_dump(mode="json"),
                    },
                }
                try:
                    await websocket.send_json(frame)
                except WebSocketDisconnect:
                    return
                await mushi.ack(stream, group, msg_id)

            # Re-fetch voyage status; close on terminal. `populate_existing`
            # bypasses the identity map so background-task writes are
            # visible (mirrors pipeline.py SSE forwarder).
            async with async_session() as live_session:
                refreshed = await live_session.get(Voyage, voyage_id, populate_existing=True)
            if refreshed is not None and refreshed.status in _TERMINAL_STATUSES:
                await _close_terminal(websocket)
                return

            if initial_terminal:
                # Already terminal at connect: forward the replayed batch
                # then close. We don't loop again because no further events
                # will be produced.
                await _close_terminal(websocket)
                return
    except WebSocketDisconnect:
        # Normal client disconnect — fall through to cleanup.
        pass
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning(
            "Unexpected error in voyage_event_stream for voyage %s",
            voyage_id,
            exc_info=True,
        )
    finally:
        try:
            await mushi._redis.xgroup_destroy(stream, group)  # noqa: SLF001
        except Exception:  # pragma: no cover - best effort cleanup
            logger.warning(
                "Failed to destroy WS consumer group %s on stream %s",
                group,
                stream,
                exc_info=True,
            )


async def _close_terminal(websocket: WebSocket) -> None:
    """Close with code 1000 + reason "voyage-terminal" (P10), best-effort."""
    if websocket.client_state == WebSocketState.CONNECTED:
        try:
            await websocket.close(code=_WS_CLOSE_NORMAL, reason=_TERMINAL_REASON)
        except RuntimeError:  # pragma: no cover - already closed
            pass
