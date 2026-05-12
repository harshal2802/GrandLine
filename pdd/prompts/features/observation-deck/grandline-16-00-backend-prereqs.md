# Phase 16.0: Observation Deck Backend Prereqs

## Context

Phase 15 (Voyage Pipeline) shipped a working backend: REST + SSE on the voyage event stream, bearer-token auth, Den Den Mushi event publishing. The Observation Deck (Phase 16) is the frontend that consumes it, but it needs a few backend additions first:

1. A durable record of crew actions for the Ship's Log (CrewAction model exists but nothing writes to it).
2. A WebSocket transport for live deck updates (per `conventions.md` line 116).
3. Cookie issuance at login so the existing Next.js middleware can gate routes.
4. A voyages list endpoint and a paginated crew-actions endpoint.

This phase adds **only** those backend pieces. Frontend work starts in Phase 16.1.

The full plan is at [pdd/prompts/features/observation-deck/PLAN-observation-deck.md](pdd/prompts/features/observation-deck/PLAN-observation-deck.md). The protocol contracts the implementation must respect are at [pdd/prompts/features/observation-deck/CONTRACTS.md](pdd/prompts/features/observation-deck/CONTRACTS.md). **Read both before starting.**

## Deliverables

### 1. CrewAction helper + locked enum (P8)

`src/backend/app/services/crew_action_helper.py`:

```python
class CrewActionType(str, enum.Enum):
    PLAN_CREATED = "plan_created"
    PONEGLYPH_DRAFTED = "poneglyph_drafted"
    HEALTH_CHECK_WRITTEN = "health_check_written"
    PHASE_BUILD_STARTED = "phase_build_started"
    PHASE_BUILD_COMPLETED = "phase_build_completed"
    PHASE_BUILD_FAILED = "phase_build_failed"
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    DEPLOYMENT_STARTED = "deployment_started"
    DEPLOYMENT_COMPLETED = "deployment_completed"
    DEPLOYMENT_FAILED = "deployment_failed"
    PIPELINE_PAUSED = "pipeline_paused"
    PIPELINE_RESUMED = "pipeline_resumed"
    PIPELINE_CANCELLED = "pipeline_cancelled"
    PIPELINE_FAILED = "pipeline_failed"
    PIPELINE_COMPLETED = "pipeline_completed"


def record_action(
    session: AsyncSession,
    voyage_id: uuid.UUID,
    crew_member: CrewRole,
    action_type: CrewActionType,
    summary: str,
    details: dict[str, Any] | None = None,
) -> CrewAction:
    """Append a CrewAction row to the caller's open transaction.

    The action is part of the same `AsyncSession` the caller is using —
    failure of the action's commit rolls back the entire service operation
    along with it (Decision 5 in the plan). The helper does NOT commit on
    its own.

    A unique `event_id` is generated and written into `details["event_id"]`
    so the frontend can dedupe a CrewActionRecordedEvent (P3 correlation
    rule). Returns the unflushed CrewAction so callers can await
    `session.flush()` if they need the row's `id` or `created_at`.
    """
```

Constraints:
- `summary` ≤ 200 chars (raise `ValueError` if longer).
- `action_type` must be a `CrewActionType` value (Pydantic / enum coercion handles validation; ad-hoc strings raise).
- `details` is merged with `{"event_id": str(uuid.uuid4())}` — never overwrite a caller-provided `event_id`; raise if one exists (callers shouldn't be guessing event ids).
- Each call adds exactly one row to the session (no commit, no flush — caller controls).

### 2. Crew service write integration

Modify each crew service to call `record_action(...)` at meaningful checkpoints, **inside the same transaction as the existing main commit**. One row per checkpoint — don't over-instrument.

| Service | Where to write | action_type | summary template | key `details` |
|---|---|---|---|---|
| [captain_service.py](src/backend/app/services/captain_service.py) — `chart_course` | After successful plan persist, before commit | `PLAN_CREATED` | `"Captain charted course with N phases"` | `{plan_id, phase_count}` |
| [navigator_service.py](src/backend/app/services/navigator_service.py) — `draft_poneglyphs` | Per Poneglyph persist | `PONEGLYPH_DRAFTED` | `"Drafted Poneglyph for phase N"` | `{poneglyph_id, phase_number}` |
| [doctor_service.py](src/backend/app/services/doctor_service.py) — `write_health_checks` | Per health check persist | `HEALTH_CHECK_WRITTEN` | `"Wrote health check for phase N"` | `{health_check_id, phase_number, framework}` |
| [doctor_service.py](src/backend/app/services/doctor_service.py) — `validate_code` (success) | Before commit | `VALIDATION_PASSED` | `"Validation passed"` | `{validation_run_id}` |
| [doctor_service.py](src/backend/app/services/doctor_service.py) — `validate_code` (failure) | Before commit | `VALIDATION_FAILED` | `"Validation failed: <short>"` | `{validation_run_id, exit_code}` |
| [shipwright_service.py](src/backend/app/services/shipwright_service.py) — `build_code` start | After phase_status flips to BUILDING, in flush | `PHASE_BUILD_STARTED` | `"Started building phase N"` | `{phase_number}` |
| [shipwright_service.py](src/backend/app/services/shipwright_service.py) — `build_code` success | Before commit | `PHASE_BUILD_COMPLETED` | `"Phase N built (X iterations, Y/Y tests passed)"` | `{phase_number, iteration_count, passed, total, duration_seconds}` |
| [shipwright_service.py](src/backend/app/services/shipwright_service.py) — `build_code` failure | Before re-raise | `PHASE_BUILD_FAILED` | `"Phase N failed: <code>"` | `{phase_number, code, message}` |
| [helmsman_service.py](src/backend/app/services/helmsman_service.py) — `deploy` start | Before backend invoke | `DEPLOYMENT_STARTED` | `"Deployment started: <tier>"` | `{deployment_id, tier, git_ref}` |
| [helmsman_service.py](src/backend/app/services/helmsman_service.py) — `deploy` success | Before commit | `DEPLOYMENT_COMPLETED` | `"Deployment completed: <tier>"` | `{deployment_id, tier, url}` |
| [helmsman_service.py](src/backend/app/services/helmsman_service.py) — `deploy` failure | Before re-raise | `DEPLOYMENT_FAILED` | `"Deployment failed: <tier>"` | `{deployment_id, tier, diagnosis}` |
| [pipeline_service.py](src/backend/app/services/pipeline_service.py) — `pause`, `resume`, `cancel` | Before commit | matching `PIPELINE_*` | terse | `{prev_status}` |
| [pipeline_service.py](src/backend/app/services/pipeline_service.py) — `start` failure path | Before re-raise | `PIPELINE_FAILED` | `"Pipeline failed at <stage>"` | `{stage, code}` |
| [pipeline_service.py](src/backend/app/services/pipeline_service.py) — `start` success | After graph completion, before logger | `PIPELINE_COMPLETED` | `"Pipeline completed in Xs"` | `{duration_seconds, deployment_url}` |

For each crew service, **extend the existing tests** to assert the relevant `CrewAction` rows appear in the test session. Aim for ~3-5 added assertions per service.

### 3. New event types (P5 reducer requires these)

Add to `src/backend/app/den_den_mushi/events.py` — new classes inheriting `DenDenMushiEvent`:

```python
class PhaseBuildStartedEvent(DenDenMushiEvent):
    event_type: Literal["phase_build_started"] = "phase_build_started"
    # payload contract (documented inline): {"phase_number": int}


class PhaseBuildFailedEvent(DenDenMushiEvent):
    event_type: Literal["phase_build_failed"] = "phase_build_failed"
    # payload contract: {"phase_number": int, "code": str, "message": str}


class CrewActionRecordedEvent(DenDenMushiEvent):
    event_type: Literal["crew_action_recorded"] = "crew_action_recorded"
    # payload contract:
    # {
    #   "crew_action_id": str (UUID),
    #   "event_id": str (UUID; matches details.event_id; P3 correlation),
    #   "action_type": str (CrewActionType value),
    #   "summary": str,
    #   "created_at": str (ISO8601; P13 canonical timestamp),
    #   "details": dict
    # }
```

All three added to the discriminated `AnyEvent` union (alphabetical or append; check existing convention).

`ShipwrightService.build_code` publishes `PhaseBuildStartedEvent` (start) and `PhaseBuildFailedEvent` (failure path), best-effort with the same `try/except` pattern Phase 15 services use. The existing `tests_passed` event already covers the BUILT transition.

`crew_action_helper.record_action` does **not** publish the `CrewActionRecordedEvent` directly — that's published by the caller after `session.commit()` succeeds, also best-effort. Add a small helper `publish_crew_action_recorded(mushi, voyage_id, crew_action) -> None` in the same file. Each service that calls `record_action` and then commits also calls `publish_crew_action_recorded` after the commit. Failure to publish does NOT roll back; the row is durable.

Extend `tests/test_den_den_mushi_events.py` with shape tests for all three new types and discrimination tests.

### 4. Observation Deck REST + WS endpoints

`src/backend/app/api/v1/observation_deck.py` (new module):

#### `GET /api/v1/voyages` — voyage list (P7)

```python
@router.get("/", response_model=VoyageListResponse)
async def list_voyages(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
    status: Literal["active", "terminal"] | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
) -> VoyageListResponse: ...
```

- Sort: `voyage.updated_at DESC, voyage.id DESC`.
- `status="active"` excludes COMPLETED, CANCELLED, FAILED. `status="terminal"` is only those.
- Cursor: opaque `base64url(JSON.stringify({ts: ISO8601, id: UUID}))`.
- SQL: `WHERE user_id = ? AND (cursor predicate) ORDER BY updated_at DESC, id DESC LIMIT <limit>`.
- Response: `{ items: VoyageListItem[], nextCursor: str | None }`. `nextCursor` is null if `len(items) < limit`.
- Authorization: only voyages owned by `user.id`.

#### `GET /api/v1/voyages/{voyage_id}/crew-actions` — paginated log (P6)

```python
@router.get("/{voyage_id}/crew-actions", response_model=CrewActionListResponse)
async def list_crew_actions(
    voyage_id: uuid.UUID,
    voyage: Voyage = Depends(get_authorized_voyage),
    session: AsyncSession = Depends(get_db),
    cursor: str | None = None,
    limit: int = Query(default=200, ge=1, le=1000),
) -> CrewActionListResponse: ...
```

- Sort: `created_at DESC, id DESC`.
- Cursor: same opaque shape, `(created_at, id)`.
- Response: `{ items: CrewActionRead[], nextCursor: str | None }`.
- `CrewActionRead` includes `details` (so the frontend gets `details.event_id` for P3 correlation).

#### `WS /api/v1/voyages/{voyage_id}/events` — live stream (P1, P10, P4)

```python
@router.websocket("/{voyage_id}/events")
async def voyage_event_stream(
    websocket: WebSocket,
    voyage_id: uuid.UUID,
    token: str,                        # query param
) -> None: ...
```

- Validates `token` (decode JWT, check user, check voyage ownership). Failure → close code **1008** (per P4 — frontend uses this to trigger refresh + reconnect).
- Voyage doesn't exist or belongs to another user → close code **1003** (Unsupported Data) so the client can distinguish from auth failures.
- Opens an ephemeral consumer group `f"sse-{uuid.uuid4().hex}"` on `stream_key(voyage_id)`. Same pattern as the existing SSE forwarder in [src/backend/app/api/v1/pipeline.py:262](src/backend/app/api/v1/pipeline.py#L262).
- Forwards every event as a JSON text frame: `{"type": "event", "payload": {"msg_id": str, "event": <model_dump>}}`. Forward-compatible envelope so Phase 17 can add `{"type": "intervention", ...}` upstream messages later.
- Each loop iteration: check if the websocket is still connected (`websocket.client_state == WebSocketState.CONNECTED` or use `websocket.receive` with a short timeout to detect disconnect — pick the cleaner pattern given starlette's API).
- Re-fetch voyage status each iteration (with `populate_existing=True` per the Phase 15.4 fix in pipeline.py). On terminal status: close with code **1000** + reason `"voyage-terminal"` (per P10).
- On client disconnect: clean up the consumer group (`xgroup_destroy`, best-effort, mirror SSE finally block).
- ack each delivered message so the consumer-group pending list stays empty.
- Block timeout ~1s on `mushi.read` calls.

### 5. Auth cookie issuance (Decision 4)

Modify `src/backend/app/api/v1/auth.py` so `/login`, `/register`, and `/refresh` set:

```
Set-Cookie: access_token=<jwt>; Path=/; SameSite=Lax; Max-Age=<token_exp_seconds>
```

- `Secure` flag added in production (gated by `settings.debug` or equivalent — match the convention in `app/core/config.py`).
- `HttpOnly` is **NOT set** — frontend JS reads the cookie to construct WS handshake URLs. Documented trade-off.
- Cookie is set in addition to the existing JSON token return — both contracts coexist.
- `/auth/refresh` updates the cookie too (so a refreshed token replaces the stale one).
- Add a `POST /auth/logout` endpoint that clears the cookie via `Set-Cookie: access_token=; Max-Age=0` and (if a refresh-token revocation exists) revokes it.

Tests in `tests/test_auth.py`:
- Login response carries `Set-Cookie` with the right shape.
- Register response carries `Set-Cookie`.
- Refresh response carries `Set-Cookie` with the new token.
- Logout response clears the cookie.
- The cookie value matches the JSON `access_token` field.

### 6. Schemas

`src/backend/app/schemas/observation_deck.py` (new module):

```python
class CrewActionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    voyage_id: uuid.UUID
    crew_member: str
    action_type: str
    summary: str
    details: dict[str, Any] | None
    created_at: datetime


class CrewActionListResponse(BaseModel):
    items: list[CrewActionRead]
    nextCursor: str | None


class VoyageListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    title: str
    description: str | None
    status: str
    target_repo: str | None
    phase_status: dict[str, str]
    created_at: datetime
    updated_at: datetime


class VoyageListResponse(BaseModel):
    items: list[VoyageListItem]
    nextCursor: str | None
```

Cursor encoding/decoding lives in a small helper module (e.g. `app/api/v1/_cursor.py`) so the same code serves both endpoints. `nextCursor` is camelCase deliberately — the frontend treats it as opaque and the JSON stays JS-idiomatic.

### 7. Router registration

Register the new router in `src/backend/app/api/v1/router.py` after the existing helmsman + pipeline routers. Tag: `"observation-deck"`.

### 8. Tests

In addition to the per-deliverable extensions called out above, add these new test files:

#### `tests/test_crew_action_helper.py`
- `record_action` adds a row to the session (no commit / no flush).
- Validates `summary` length.
- Rejects ad-hoc strings via Pydantic (P8).
- Generates `event_id` and merges into `details`; rejects pre-set `event_id`.
- `publish_crew_action_recorded` builds the right event payload shape.

#### `tests/test_observation_deck_api.py` (REST)
- `GET /voyages`: returns only owner's voyages; status filter excludes correctly; default sort `(updated_at, id)` DESC; cursor pagination stable across equal `updated_at`; invalid cursor → 400.
- `GET /voyages/{id}/crew-actions`: 404 on foreign voyage; cursor stable across equal `created_at`; default sort `(created_at, id)` DESC; nextCursor is null at end.

#### `tests/test_observation_deck_ws.py` (WS)

Uses starlette's `TestClient.websocket_connect` (synchronous-style API) OR `httpx-ws` if it's already a dep — pick whichever the project's other infra suggests.

- Happy path: open with valid token + voyage ownership → receives a forwarded event after one is published.
- Auth failure: missing token / invalid token / expired token → close code 1008.
- Voyage not found / not owned → close code 1003.
- Voyage already terminal at connect time → forwards any replayed events then closes with 1000 + reason `"voyage-terminal"`.
- Voyage flips to terminal mid-stream → close code 1000 + reason `"voyage-terminal"`.
- Client disconnect → server cleans up consumer group (best-effort).
- Forwarded frame shape matches `{"type": "event", "payload": {"msg_id": str, "event": dict}}`.

#### Integration test extension
Optionally extend `tests/integration/test_pipeline_integration.py` so the happy-path test asserts that `crew_actions` rows appeared for the major checkpoints. Don't over-test here; the integration baseline is already comprehensive.

## Verification before declaring done

From `src/backend/`:

1. `python3 -m ruff check app/ tests/` — clean.
2. `python3 -m mypy app/ --ignore-missing-imports` — clean.
3. `python3 -m pytest -q` — full suite green; no regressions on the existing 837 unit tests.
4. `python3 -m pytest -m integration tests/integration/ -q` — 9 tests still passing (expected to remain at 9 unless the integration extension adds one).

If any test fails, fix before declaring done.

## Constraints

- **No frontend code in this phase.** Frontend starts in 16.1.
- **Don't change Phase 15 application logic.** Crew services gain `record_action` calls but their existing behavior must be unchanged. Existing tests must still pass.
- **CrewAction is durable**: writes are part of the same transaction as the main service commit. A failed CrewAction insert rolls back the whole operation.
- **Event publishing remains best-effort**: `CrewActionRecordedEvent` is published after the commit; failure logs but doesn't roll anything back. The durable record is the DB row.
- **Cursor encoding is stable**: round-trip through `cursor.encode → decode → encode` produces the same string. Tests verify.
- **WS endpoint pattern matches the SSE forwarder** in pipeline.py — same consumer-group lifecycle, same `populate_existing=True` voyage status check, same cleanup on disconnect.
- **`record_action` raises on bad input**, doesn't silently swallow.
- **No new database migrations** — `crew_actions` table exists; we just write to it.
- **Don't refactor** existing crew services beyond adding the `record_action` calls + the two new ShipwrightService event publishes. No drive-by cleanups.
- **No commit or PR until the user signs off.**

## Test plan

- [ ] All Phase 16.0 deliverables compile and pass mypy.
- [ ] `tests/test_crew_action_helper.py` passes.
- [ ] `tests/test_observation_deck_api.py` passes.
- [ ] `tests/test_observation_deck_ws.py` passes.
- [ ] `tests/test_den_den_mushi_events.py` extensions pass.
- [ ] `tests/test_auth.py` extensions pass.
- [ ] Each extended crew-service test passes with the new CrewAction assertions.
- [ ] Full unit suite still green (~ 850+ tests with new additions).
- [ ] Integration suite still passes (9 tests).
- [ ] `make smoke` (Phase 15.4 manual harness) still works.

## References

- Plan: [PLAN-observation-deck.md](PLAN-observation-deck.md)
- Contracts: [CONTRACTS.md](CONTRACTS.md)
- CrewAction model: [src/backend/app/models/crew_action.py](src/backend/app/models/crew_action.py)
- SSE forwarder pattern: [src/backend/app/api/v1/pipeline.py — stream_events](src/backend/app/api/v1/pipeline.py#L262)
- Existing events: [src/backend/app/den_den_mushi/events.py](src/backend/app/den_den_mushi/events.py)
- Auth router: [src/backend/app/api/v1/auth.py](src/backend/app/api/v1/auth.py)
- API router: [src/backend/app/api/v1/router.py](src/backend/app/api/v1/router.py)
