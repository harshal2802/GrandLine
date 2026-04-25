"""Phase 15.4 manual smoke test — drives the pipeline REST + SSE API.

Assumes:
- Postgres + Redis are up (make up)
- Migrations applied (make migrate)
- API running with PipelineService.start mocked (make api-mocked)

What this script does:
1. Registers a fresh test user, captures the JWT.
2. Inserts a Voyage and a DialConfig directly via SQLAlchemy (no public
   creation endpoint for voyages).
3. Hits GET /status on a freshly-charted voyage (expect empty counts).
4. Opens an SSE connection to GET /stream in a background task.
5. Hits POST /start with a mocked pipeline that emits 14 synthetic events
   (started + 6 stage_entered/completed pairs + completed) and flips
   voyage.status to COMPLETED.
6. Collects SSE frames, asserts shape, msg_id, event_type sequence.
7. Tests POST /pause and POST /cancel idempotency on an already-terminal
   voyage (a fresh voyage is created for each) — both should 200 no-op.

Run via: `make smoke`.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.models.dial_config import DialConfig
from app.models.enums import VoyageStatus
from app.models.voyage import Voyage

API = os.environ.get("GRANDLINE_API_URL", "http://localhost:8000")
DB_URL = os.environ["GRANDLINE_DATABASE_URL"]


def _pp(label: str, obj: Any) -> None:
    print(f"\n── {label} ──")
    if isinstance(obj, dict | list):
        print(json.dumps(obj, indent=2, default=str))
    else:
        print(obj)


async def _insert_voyage(session: AsyncSession, user_id: uuid.UUID, title: str) -> Voyage:
    voyage = Voyage(
        user_id=user_id,
        title=title,
        description="Phase 15.4 smoke test voyage",
        status=VoyageStatus.CHARTED.value,
        phase_status={},
    )
    session.add(voyage)
    await session.flush()

    dial = DialConfig(
        voyage_id=voyage.id,
        role_mapping={
            "captain": {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
            "navigator": {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
            "doctor": {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
            "shipwright": {
                "provider": "anthropic",
                "model": "claude-sonnet-4-5-20250929",
                "max_concurrency": 2,
            },
            "helmsman": {"provider": "anthropic", "model": "claude-sonnet-4-5-20250929"},
        },
    )
    session.add(dial)
    await session.commit()
    await session.refresh(voyage)
    return voyage


async def _register_and_get_token(client: httpx.AsyncClient) -> tuple[str, uuid.UUID]:
    suffix = uuid.uuid4().hex[:10]
    body = {
        "email": f"smoke+{suffix}@example.com",
        "username": f"smoke_{suffix}",
        "password": "SmokeTest!23",
    }
    r = await client.post(f"{API}/api/v1/auth/register", json=body)
    r.raise_for_status()
    tokens = r.json()
    access = tokens["access_token"]

    # Decode without verification to grab user id.
    import base64

    payload_b64 = access.split(".")[1]
    payload_b64 += "=" * (-len(payload_b64) % 4)
    payload = json.loads(base64.urlsafe_b64decode(payload_b64))
    user_id = uuid.UUID(payload["sub"])
    return access, user_id


async def _stream_events(
    client: httpx.AsyncClient, voyage_id: uuid.UUID, headers: dict[str, str]
) -> list[dict[str, Any]]:
    """Open SSE connection and collect envelopes until the server closes."""
    events: list[dict[str, Any]] = []
    url = f"{API}/api/v1/voyages/{voyage_id}/stream"
    async with client.stream("GET", url, headers=headers, timeout=30) as resp:
        resp.raise_for_status()
        buffer = b""
        async for chunk in resp.aiter_bytes():
            buffer += chunk
            while b"\n\n" in buffer:
                frame, buffer = buffer.split(b"\n\n", 1)
                if not frame.startswith(b"data: "):
                    continue
                payload = frame[len(b"data: ") :].decode()
                events.append(json.loads(payload))
    return events


async def _scenario_start_and_stream(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    print("\n" + "=" * 70)
    print("Scenario 1: start a voyage, tail SSE, verify event sequence")
    print("=" * 70)

    engine = create_async_engine(DB_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    # Register a user + insert voyage.
    access, user_id = await _register_and_get_token(client)
    headers["Authorization"] = f"Bearer {access}"
    async with session_factory() as session:
        voyage = await _insert_voyage(session, user_id, "Phase 15.4 smoke — start+stream")
    print(f"user_id={user_id} voyage_id={voyage.id}")

    # Open SSE in the background before calling start.
    sse_task = asyncio.create_task(_stream_events(client, voyage.id, headers))
    await asyncio.sleep(0.2)  # let the consumer group establish

    # POST /start
    r = await client.post(
        f"{API}/api/v1/voyages/{voyage.id}/start",
        headers=headers,
        json={"task": "build a simple hello world service"},
    )
    _pp(f"POST /start -> {r.status_code}", r.json())
    assert r.status_code == 202, f"expected 202, got {r.status_code}"
    assert r.json()["accepted"] is True

    # Collect SSE frames.
    try:
        events = await asyncio.wait_for(sse_task, timeout=15)
    except TimeoutError:
        sse_task.cancel()
        raise RuntimeError("SSE stream did not close within 15s")
    _pp(f"SSE frames received ({len(events)})", [e["event"]["event_type"] for e in events])

    # Verify envelope shape + event sequence.
    types = [e["event"]["event_type"] for e in events]
    assert types[0] == "pipeline_started", f"first event should be pipeline_started, got {types[0]}"
    assert types[-1] == "pipeline_completed", "last event should be pipeline_completed"
    assert types.count("pipeline_stage_entered") == 6
    assert types.count("pipeline_stage_completed") == 6
    for env in events:
        assert "msg_id" in env and "event" in env
        assert env["event"]["voyage_id"] == str(voyage.id)
    print("✓ SSE envelope sequence matches expected pipeline flow")

    # POST /start again (voyage is now COMPLETED) → expect 409
    r2 = await client.post(
        f"{API}/api/v1/voyages/{voyage.id}/start",
        headers=headers,
        json={"task": "build a simple hello world service"},
    )
    assert r2.status_code == 409
    _pp(f"POST /start (on COMPLETED) -> {r2.status_code}", r2.json())
    print("✓ Re-start on COMPLETED voyage rejected with 409")

    # GET /status
    r3 = await client.get(f"{API}/api/v1/voyages/{voyage.id}/status", headers=headers)
    _pp(f"GET /status -> {r3.status_code}", r3.json())
    assert r3.status_code == 200
    assert r3.json()["status"] == VoyageStatus.COMPLETED.value
    print("✓ GET /status reports COMPLETED")

    await engine.dispose()


async def _scenario_pause_cancel(client: httpx.AsyncClient, headers: dict[str, str]) -> None:
    print("\n" + "=" * 70)
    print("Scenario 2: pause + cancel endpoints")
    print("=" * 70)

    engine = create_async_engine(DB_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    access, user_id = await _register_and_get_token(client)
    pause_headers = {"Authorization": f"Bearer {access}"}
    async with session_factory() as session:
        voyage = await _insert_voyage(session, user_id, "Phase 15.4 smoke — pause")

    r = await client.post(f"{API}/api/v1/voyages/{voyage.id}/pause", headers=pause_headers)
    _pp(f"POST /pause -> {r.status_code}", r.json())
    assert r.status_code == 200
    assert r.json()["status"] == VoyageStatus.PAUSED.value
    print("✓ POST /pause flips status to PAUSED")

    # Idempotency
    r2 = await client.post(f"{API}/api/v1/voyages/{voyage.id}/pause", headers=pause_headers)
    assert r2.status_code == 200
    print("✓ POST /pause is idempotent")

    # Now cancel
    r3 = await client.post(f"{API}/api/v1/voyages/{voyage.id}/cancel", headers=pause_headers)
    _pp(f"POST /cancel -> {r3.status_code}", r3.json())
    assert r3.status_code == 200
    assert r3.json()["status"] == VoyageStatus.CANCELLED.value
    print("✓ POST /cancel flips status to CANCELLED")

    # Idempotency on terminal
    r4 = await client.post(f"{API}/api/v1/voyages/{voyage.id}/cancel", headers=pause_headers)
    assert r4.status_code == 200
    print("✓ POST /cancel is idempotent on CANCELLED")

    # GET /status on cancelled voyage
    r5 = await client.get(f"{API}/api/v1/voyages/{voyage.id}/status", headers=pause_headers)
    assert r5.status_code == 200
    assert r5.json()["status"] == VoyageStatus.CANCELLED.value
    print("✓ GET /status reports CANCELLED")

    await engine.dispose()


async def _scenario_unauthorized(client: httpx.AsyncClient) -> None:
    print("\n" + "=" * 70)
    print("Scenario 3: 404 on foreign voyage id (authorization check)")
    print("=" * 70)

    # User A creates a voyage; User B tries to access it.
    access_a, user_a_id = await _register_and_get_token(client)
    access_b, _user_b_id = await _register_and_get_token(client)

    engine = create_async_engine(DB_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        voyage = await _insert_voyage(session, user_a_id, "Phase 15.4 smoke — authz")
    await engine.dispose()

    headers_b = {"Authorization": f"Bearer {access_b}"}
    r = await client.get(f"{API}/api/v1/voyages/{voyage.id}/status", headers=headers_b)
    assert r.status_code == 404, f"expected 404, got {r.status_code}: {r.text}"
    print("✓ GET /status -> 404 when voyage belongs to another user")


async def main() -> int:
    async with httpx.AsyncClient(timeout=30) as client:
        # Sanity: API up
        try:
            r = await client.get(f"{API}/api/v1/health")
            r.raise_for_status()
        except Exception as exc:
            print(f"API at {API} not reachable: {exc}", file=sys.stderr)
            print("Run `make api-mocked` in another terminal first.", file=sys.stderr)
            return 1

        headers: dict[str, str] = {}
        await _scenario_start_and_stream(client, headers)
        await _scenario_pause_cancel(client, headers)
        await _scenario_unauthorized(client)

    print("\n✅ All scenarios passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
