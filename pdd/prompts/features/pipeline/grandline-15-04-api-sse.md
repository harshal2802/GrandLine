# Phase 15.4: Pipeline REST + SSE API

## Context

Phase 15.3 landed the master Voyage Pipeline graph
([pipeline_graph.py](src/backend/app/crew/pipeline_graph.py)),
`PipelineService` orchestrator
([pipeline_service.py](src/backend/app/services/pipeline_service.py)),
and five pipeline-level events (Started / StageEntered / StageCompleted /
Completed / Failed) on the Den Den Mushi stream. `PipelineService.start()`
runs the graph to completion synchronously in the caller's event loop. No
HTTP endpoints, no background tasks, no SSE — all intentionally deferred
to this phase.

Phase 15.4 is the **API layer**: five REST endpoints plus one SSE stream,
plus the dependency-injection and background-task wiring needed to spawn
the graph run without blocking the request. After this phase the frontend
can start a voyage, observe it live over SSE, pause/cancel mid-run, and
poll status — feature-complete from a user perspective. Phase 15.5 will
add the full-stack integration test with real Postgres + Redis.

**Locked decisions driving this phase** (see
[PLAN-voyage-pipeline.md](PLAN-voyage-pipeline.md)):

- **Background task runner lives at the API layer.** `POST /start` spawns
  the pipeline via `asyncio.create_task(service.start(...))` and records
  the task in `app.state.pipeline_tasks: dict[uuid.UUID, asyncio.Task]`
  keyed by voyage id. The task callback removes itself from the registry
  on completion (success or failure). The service stays sync-to-graph-
  completion; only the endpoint wraps it in a task.
- **SSE semantics**: `data: {json}\n\n` frames, no named events, fresh
  consumer group per connection (`f"sse-{uuid.uuid4().hex}"`), short
  block timeout (~1s) with disconnect check each iteration. Termination
  on voyage terminal status (`COMPLETED` | `FAILED` | `CANCELLED`).
- **Idempotency on POST /start**: running pipeline → 409;
  COMPLETED → 409 (force re-run is out of scope; cancel + restart is the
  workaround). `CHARTED` / `PAUSED` / `FAILED` → accept.
- **POST /pause** and **POST /cancel**: write voyage.status to PAUSED /
  CANCELLED and commit. The running graph observes the new status at
  the next stage boundary (PipelineService already implements this in
  each stage node). If no pipeline is running, both are idempotent
  no-ops on terminal status; on PAUSED calling pause again is a no-op,
  on CANCELLED calling cancel again is a no-op.
- **GET /status** uses `PipelineService.reader(session)` — a read-only
  variant that constructs without the live dial router / execution
  backend / mushi. Returns `PipelineStatusSnapshot` unchanged from
  Phase 15.3, wrapped in a thin response envelope.
- **Authorization**: reuse the existing `get_authorized_voyage`
  dependency ([dependencies.py:89-103](src/backend/app/api/v1/dependencies.py#L89-L103))
  — 404 if voyage doesn't exist or belongs to another user. No separate
  pipeline permission model.
- **Concurrency override validation**: `StartVoyageRequest.max_parallel_shipwrights`
  is `int | None` with `Field(ge=1, le=10)`. `None` falls through to
  DialConfig then to the default of 1, matching `PipelineService._resolve_concurrency`
  ([pipeline_service.py:258-275](src/backend/app/services/pipeline_service.py#L258-L275)).
- **`deploy_tier` is `Literal["preview"]`** — only preview is wired in
  this phase; staging / production come later with their own approval
  flow. Matches the Phase 15.3 service signature.
- **SSE replay-from-start by default** — fresh consumer groups created
  at `id="0"` so a late-connecting client sees every event emitted for
  the voyage so far. No `last-event-id` support in this phase; clients
  that reconnect get the full stream again.
- **Background task registry is process-local** — `app.state.pipeline_tasks`
  is an in-memory dict. Multi-worker deployments are out of scope for
  v1; the fleet runs single-worker. Tests cover task cleanup on
  completion + cancellation.

## Deliverables

### 1. Schemas: `app/schemas/pipeline.py`

**Extend the existing file** (already contains `PipelineStatusSnapshot`).
Add three new models:

```python
class StartVoyageRequest(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")

    task: str = Field(min_length=10, max_length=5000)
    deploy_tier: Literal["preview"] = "preview"
    max_parallel_shipwrights: int | None = Field(default=None, ge=1, le=10)


class StartVoyageResponse(BaseModel):
    model_config = ConfigDict(strict=True)

    voyage_id: uuid.UUID
    status: str              # voyage.status after start (PLANNING typically)
    accepted: bool = True    # always True on 202; explicit for client clarity


class PipelineEventEnvelope(BaseModel):
    """Wire envelope sent over SSE for each Redis stream message."""

    model_config = ConfigDict(strict=True)

    msg_id: str              # Redis stream message id (for client dedup)
    event: dict[str, Any]    # parsed event JSON (event_type, voyage_id, payload, ...)
```

`StartVoyageRequest.task` mirrors Captain's
[ChartCourseRequest.task](src/backend/app/schemas/captain.py#L72-L73)
constraints. Don't duplicate the validator — just match the length
constraints on the field.

### 2. Dependencies: `app/api/v1/dependencies.py`

**Add two new dependency functions** alongside the existing ones:

```python
def get_pipeline_service(
    voyage_id: uuid.UUID,
    dial_router: DialSystemRouter = Depends(get_dial_router),
    mushi: DenDenMushi = Depends(get_den_den_mushi),
    session: AsyncSession = Depends(get_db),
    execution_service: ExecutionService = Depends(get_execution_service),
    git_service: GitService = Depends(get_git_service),
    deployment_backend: DeploymentBackend = Depends(get_deployment_backend),
) -> PipelineService:
    return PipelineService(
        session=session,
        mushi=mushi,
        dial_router=dial_router,
        execution_service=execution_service,
        git_service=git_service,
        deployment_backend=deployment_backend,
    )


async def get_pipeline_service_reader(
    session: AsyncSession = Depends(get_db),
) -> PipelineService:
    return PipelineService.reader(session)
```

Mirror the shape of
[helmsman.py:get_helmsman_service / get_helmsman_reader](src/backend/app/api/v1/helmsman.py#L53-L73).
No changes to existing dependencies.

### 3. Pipeline router: `app/api/v1/pipeline.py` (new)

**`POST /voyages/{voyage_id}/start` → 202**:
- Body: `StartVoyageRequest`.
- Guards: call `require_can_enter_planning(voyage)` eagerly (via
  `PipelineService.start` internally) — translate `PipelineError` to HTTP
  409 for `VOYAGE_NOT_PLANNABLE`, 400 for `INVALID_CONCURRENCY`, 422
  otherwise.
- **Running-pipeline idempotency**: if
  `voyage_id in request.app.state.pipeline_tasks` and that task is not
  yet done → 409 `{"code": "PIPELINE_ALREADY_RUNNING", ...}`.
- Spawn `asyncio.create_task(service.start(voyage, user.id, body.task,
  body.deploy_tier, body.max_parallel_shipwrights))`.
- Register in `request.app.state.pipeline_tasks[voyage_id] = task`.
- Attach `task.add_done_callback(lambda t: app.state.pipeline_tasks.pop(voyage_id, None))`.
- Return `StartVoyageResponse(voyage_id=voyage_id, status=voyage.status)`.
  The status is read from the **pre-spawn** voyage (typically `CHARTED`
  if never run, or whatever state it was in). The service will update it
  inside the task.

**`POST /voyages/{voyage_id}/pause` → 200**:
- Calls `PipelineService.pause(voyage)`. Idempotent on terminal statuses
  (handled in the service). Returns `{"voyage_id", "status"}`.

**`POST /voyages/{voyage_id}/cancel` → 200**:
- Calls `PipelineService.cancel(voyage)`. Also cancels the in-flight
  background task if present: `task.cancel()`. Return
  `{"voyage_id", "status"}`. Do not `await` the cancelled task in the
  request; the done_callback will clean up the registry.

**`GET /voyages/{voyage_id}/status` → 200**:
- Calls `PipelineService.reader(session).get_status(voyage)`. Returns
  `PipelineStatusSnapshot` directly as the response body.

**`GET /voyages/{voyage_id}/stream` → 200 text/event-stream**:
- SSE endpoint. Implementation outline:
  ```python
  @router.get("/stream")
  async def stream_events(...) -> StreamingResponse:
      async def event_generator() -> AsyncGenerator[bytes, None]:
          group = f"sse-{uuid.uuid4().hex}"
          await mushi.ensure_group(stream_key(voyage.id), group)
          consumer = f"sse-{uuid.uuid4().hex[:8]}"
          try:
              while True:
                  if await request.is_disconnected():
                      break
                  batch = await mushi.read(
                      stream=stream_key(voyage.id),
                      group=group,
                      consumer=consumer,
                      count=10,
                      block_ms=1000,
                  )
                  for msg_id, event in batch:
                      envelope = PipelineEventEnvelope(
                          msg_id=msg_id, event=event.model_dump(mode="json")
                      )
                      yield f"data: {envelope.model_dump_json()}\n\n".encode()
                      await mushi.ack(stream_key(voyage.id), group, msg_id)
                  # re-fetch voyage status; close on terminal
                  refreshed = await session.get(Voyage, voyage.id)
                  if refreshed and refreshed.status in {
                      VoyageStatus.COMPLETED.value,
                      VoyageStatus.FAILED.value,
                      VoyageStatus.CANCELLED.value,
                  }:
                      break
          finally:
              # best-effort group cleanup: xgroup_destroy on the fresh group
              try:
                  await redis.xgroup_destroy(stream_key(voyage.id), group)
              except Exception:
                  pass
      return StreamingResponse(event_generator(), media_type="text/event-stream")
  ```
- `mushi.read` returns `list[tuple[msg_id, DenDenMushiEvent]]`, matches
  [mushi.py:32-68](src/backend/app/den_den_mushi/mushi.py#L32-L68).
- Fresh ephemeral consumer group means each SSE connection replays from
  `id="0"` (mushi.ensure_group default). Clients that reconnect see the
  full history again — acceptable for v1.
- Acknowledge each delivered message so the pending list stays empty.
- Check `request.is_disconnected()` each iteration; bail cleanly on
  client close.
- On exit, destroy the group so Redis doesn't accumulate per-connection
  groups. Best-effort; warn-and-swallow on failure.

**HTTP error mapping** — mirror
[helmsman.py:_helmsman_http_exception](src/backend/app/api/v1/helmsman.py#L45-L50):

| PipelineError code | HTTP status |
|---|---|
| `VOYAGE_NOT_PLANNABLE` | 409 Conflict |
| `PIPELINE_ALREADY_RUNNING` | 409 Conflict |
| `INVALID_CONCURRENCY` | 400 Bad Request |
| (anything else) | 422 Unprocessable Entity |

Body shape: `{"error": {"code": "<CODE>", "message": "..."}}` — matches
the project-wide convention.

**Router registration**: include the new router in
[app/api/v1/router.py](src/backend/app/api/v1/router.py) right after
the helmsman router. Tag: `"pipeline"`.

### 4. App state wiring: `app/main.py`

**Initialize `app.state.pipeline_tasks`** in the FastAPI lifespan (or
equivalent startup hook). Shape:
`app.state.pipeline_tasks: dict[uuid.UUID, asyncio.Task[None]] = {}`.
Nothing else changes in `main.py` — the dial router, mushi, execution
service, git service, and deployment backend are already attached to
`app.state` from earlier phases.

On shutdown, cancel any still-running tasks and await them with a short
timeout (5s) to give them a chance to emit `PipelineFailedEvent` before
the process exits. Log warnings if any tasks don't finish in time.

### 5. Tests: `tests/test_pipeline_api.py` (new)

Follow the structure of
[tests/test_helmsman_api.py](src/backend/tests/test_helmsman_api.py).
Use `httpx.AsyncClient` via the existing `async_client` fixture. All
crew services mocked at the `PipelineService` boundary (monkeypatch
`PipelineService.start`, `.pause`, `.cancel`, `.get_status`). For SSE,
use `httpx.AsyncClient.stream("GET", ...)` and iterate events.

**`TestStartVoyage`**:
- `test_start_returns_202_and_spawns_task` — happy path, assert
  registry entry present, task awaited eventually
- `test_start_rejects_running_pipeline_with_409`
- `test_start_translates_voyage_not_plannable_to_409`
- `test_start_translates_invalid_concurrency_to_400`
- `test_start_validates_task_length` — `task=""` → 422 (Pydantic)
- `test_start_validates_max_parallel_range` — 0 → 422, 11 → 422
- `test_start_forbidden_for_other_users_voyage` — 404 via
  `get_authorized_voyage`
- `test_start_task_removes_itself_from_registry_on_completion` —
  confirm `done_callback` pops the entry

**`TestPauseVoyage`** / **`TestCancelVoyage`**:
- `test_pause_returns_200_and_sets_status_paused`
- `test_pause_is_idempotent_on_paused`
- `test_pause_is_idempotent_on_terminal`
- `test_cancel_returns_200_and_sets_status_cancelled`
- `test_cancel_is_idempotent_on_terminal`
- `test_cancel_also_cancels_running_task` — start a task, POST /cancel,
  assert `task.cancelled()` within timeout

**`TestGetStatus`**:
- `test_status_returns_snapshot_shape`
- `test_status_uses_pipeline_reader_not_full_service` — assert no
  dial router / execution service construction during a status call
  (patch `get_pipeline_service` and confirm it's NOT invoked)
- `test_status_forbidden_for_other_users_voyage` — 404

**`TestStreamEvents`**:
- `test_stream_emits_events_from_redis_and_closes_on_completion` —
  seed the Redis stream with three events ending in
  `PipelineCompletedEvent`, open the SSE connection, collect frames,
  assert three `data: ...` frames and a clean close
- `test_stream_replays_from_start_for_fresh_connection` — pre-seed
  two events, then connect, assert both replayed before live updates
- `test_stream_closes_on_client_disconnect` — open, close client,
  assert generator exits within short timeout
- `test_stream_closes_on_voyage_failure` — emit
  `PipelineFailedEvent`, flip voyage.status to FAILED, assert close
- `test_stream_emits_valid_sse_frames` — each chunk matches
  `^data: .+\n\n$` and envelope is JSON-parseable
- `test_stream_forbidden_for_other_users_voyage` — 404

**`TestPipelineSchemas`**:
- `test_start_voyage_request_rejects_extra_fields`
- `test_start_voyage_request_strict_types` — `max_parallel_shipwrights="2"`
  (string) → validation error under `strict=True`
- `test_pipeline_event_envelope_round_trip`

**Test fixtures**:
- Add `pipeline_tasks_registry` fixture that clears
  `app.state.pipeline_tasks` before and after each test.
- Reuse `authorized_voyage`, `async_client`, and `mushi_stream`
  fixtures from the existing conftest if present; add them if not.
- Mock `PipelineService.start` as an `AsyncMock` that sleeps briefly
  (`await asyncio.sleep(0.05)`) so task-cleanup callbacks have a chance
  to fire before assertions.
- For SSE tests, use the real `DenDenMushi` + `fakeredis` if the
  project already uses fakeredis, else an in-memory stub matching the
  `mushi.read` contract. Check existing Redis-using tests
  ([test_den_den_mushi_mushi.py](src/backend/tests/test_den_den_mushi_mushi.py))
  for the established pattern.

### 6. No service changes

- Do NOT modify `PipelineService`, `pipeline_graph`, any crew service,
  or any existing schema. This phase is pure API surface on top of
  Phase 15.3.
- Do NOT add new event types; the five from Phase 15.3 are sufficient.
- Do NOT touch crew routers or dependencies unrelated to the pipeline.

## Test Plan

- [ ] All new tests in `tests/test_pipeline_api.py` pass
- [ ] `ruff check app/ tests/` clean
- [ ] `mypy app/` clean
- [ ] All existing tests (780+) still pass — this phase only adds code
- [ ] SSE test sends at least three events and the client receives all
  of them before the stream closes
- [ ] Background task registry: after a full happy-path test,
  `app.state.pipeline_tasks` is empty (done_callback fired)
- [ ] `POST /start` with a running pipeline returns 409 with
  `PIPELINE_ALREADY_RUNNING` code
- [ ] `POST /cancel` cancels both the DB status and the `asyncio.Task`
- [ ] `GET /status` does not construct a dial router (pure read path)
- [ ] Log one decision to
  [pdd/context/decisions.md](pdd/context/decisions.md) (see Constraints)

## Constraints

- **API-only phase** — no changes to `PipelineService`, `pipeline_graph`,
  or any crew service. Every behavior difference is at the HTTP layer.
- **Background task registry is in-memory** — `app.state.pipeline_tasks`
  is a `dict[uuid.UUID, asyncio.Task]`. Multi-worker is out of scope;
  single worker only. Document the limitation in a one-line comment.
- **`done_callback` cleans up the registry** — on success OR exception
  OR cancellation. A task that dies without removing itself is a bug.
- **SSE uses fresh ephemeral consumer groups** — one per connection,
  replay-from-start (`id="0"`), destroyed on disconnect. Do NOT reuse
  a shared group name across connections.
- **Terminate SSE on voyage terminal status** — poll the DB between
  reads, exit when `COMPLETED | FAILED | CANCELLED`. Don't rely on a
  dedicated terminator event.
- **Check `request.is_disconnected()` each loop** — clients closing
  the connection must release the Redis consumer within ~1s.
- **Block timeout ~1s** — balances responsiveness with Redis load.
  Use `BLOCK_MS` from
  [den_den_mushi/constants.py](src/backend/app/den_den_mushi/constants.py)
  if a constant already exists; otherwise hardcode `1000`.
- **Acknowledge every delivered SSE message** — pending list stays
  empty per connection.
- **Authorization via `get_authorized_voyage`** — don't invent a new
  permission model. 404 on foreign voyage is correct.
- **Error envelope shape** — `{"error": {"code", "message"}}` matches
  the project-wide convention (see
  [helmsman.py:45-50](src/backend/app/api/v1/helmsman.py#L45-L50)).
- **`POST /start` is 202, not 201** — it accepts the request and
  returns immediately; work continues in the background.
- **Idempotency on running pipeline is 409, not 200** — callers must
  explicitly decide to cancel+restart.
- **`deploy_tier` is `Literal["preview"]` only** — staging / prod come
  with the approval flow in a later phase. Pydantic rejects other
  values with 422.
- **`max_parallel_shipwrights: int | None`** — `None` falls through to
  DialConfig → default 1. Explicit `int` must satisfy `1 <= x <= 10`.
- **Shutdown cancels in-flight tasks with 5s await** — emit final
  events, then let the loop exit. Warn on tasks that don't respond.
- **No `last-event-id` / SSE resume** — client reconnects get the full
  replay. Revisit if stream volume grows.
- **Log one decision** to
  [pdd/context/decisions.md](pdd/context/decisions.md). Suggested text:
  *"Phase 15.4 (2026-04-24): Pipeline REST + SSE API. POST /start is
  202 + background task, registered in `app.state.pipeline_tasks` and
  cleaned up via done_callback. Running-pipeline idempotency returns
  409. SSE uses fresh ephemeral consumer groups per connection
  (replay-from-start), terminates on voyage terminal status, and
  checks `request.is_disconnected()` each ~1s iteration. No
  `last-event-id` resume in v1. Background task registry is
  process-local; multi-worker is out of scope."*
- **No commit or PR until the user signs off.**

## References

- Plan: [PLAN-voyage-pipeline.md](PLAN-voyage-pipeline.md) (Phase 4)
- Phase 15.3: [PR #37](https://github.com/harshal2802/GrandLine/pull/37) —
  `PipelineService`, `pipeline_graph`, pipeline events,
  `PipelineStatusSnapshot`
- Service contract (don't modify):
  - [pipeline_service.py](src/backend/app/services/pipeline_service.py) —
    `start(voyage, user_id, task, deploy_tier, max_parallel_shipwrights)`,
    `pause`, `cancel`, `get_status`, `reader(session)`
  - [pipeline_graph.py](src/backend/app/crew/pipeline_graph.py) —
    stage nodes, terminal nodes, event emission
- SSE / Redis primitives:
  - [den_den_mushi/mushi.py](src/backend/app/den_den_mushi/mushi.py) —
    `publish`, `ensure_group`, `read`, `ack`
  - [den_den_mushi/constants.py](src/backend/app/den_den_mushi/constants.py) —
    `stream_key(voyage_id)`, `BLOCK_MS`
  - [den_den_mushi/events.py](src/backend/app/den_den_mushi/events.py) —
    event types + `AnyEvent` union (Phase 15.3 added the five pipeline
    events)
- API conventions (copy the shape):
  - [api/v1/helmsman.py](src/backend/app/api/v1/helmsman.py) —
    router structure, error mapping, dependency injection
  - [api/v1/dependencies.py](src/backend/app/api/v1/dependencies.py) —
    `get_authorized_voyage`, `get_current_user`, existing DI helpers
  - [api/v1/router.py](src/backend/app/api/v1/router.py) — where to
    register the new router
- Voyage model (for status transitions):
  [models/voyage.py](src/backend/app/models/voyage.py) + `VoyageStatus`
  enum in [models/enums.py](src/backend/app/models/enums.py)
- Schema module (to extend):
  [schemas/pipeline.py](src/backend/app/schemas/pipeline.py) — already
  contains `PipelineStatusSnapshot`
