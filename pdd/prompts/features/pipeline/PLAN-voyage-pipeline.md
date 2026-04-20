# Implementation Plan: Voyage Pipeline (Phase 15)

**Created**: 2026-04-18
**Revised**: 2026-04-19 — add parallel Shipwright + `phase_status` refactor + configurable concurrency
**Issue**: #16
**Complexity**: High — first integration across all five crew services; new state machine + guard helpers; parallel-safe Shipwright refactor; background runner; SSE forwarding; end-to-end integration test.
**Estimated prompts**: 5

## Summary

The master LangGraph wires the existing five crew services (Captain → Navigator → Doctor-writes → Shipwright-per-phase-in-parallel → Doctor-validates → Helmsman) into one end-to-end pipeline with a formal state machine and transition guards.

Nodes are **thin service adapters** — each service owns its DB commit, VivreCard checkpoints, and best-effort event publishing. The master graph's job is: check pre-conditions, invoke the service, translate failures into a `FAILED` voyage, and emit pipeline-level events.

Shipwright gains a **per-phase status gate** (`Voyage.phase_status` JSONB) so multiple phases can build concurrently without racing. The pipeline runs Shipwright phases in **topological layers** — all dep-free phases in parallel, wait, next layer, etc. Concurrency is bounded by a user-configurable `max_concurrency` setting stored in `DialConfig.role_mapping.shipwright` (default 1, ceiling 10).

`POST /voyages/{id}/start` kicks the graph off as a background task (`asyncio.create_task`). `GET /voyages/{id}/status` returns current status + progress summary. `GET /voyages/{id}/stream` is an SSE forwarder that tails the voyage's existing Den Den Mushi stream key.

## Locked-in design decisions

These are the seven design decisions resolved. Each needs a line logged in `pdd/context/decisions.md` as part of the relevant phase.

### (1) Master graph invokes services directly (not sub-graphs)

**Decision**: Graph nodes are thin async wrappers that call `CaptainService.chart_course(...)`, `NavigatorService.draft_poneglyphs(...)`, etc. Each service already owns DB writes, status transitions, VivreCard checkpointing, and best-effort event publishing.

**Why**: The sub-graphs are pure LLM/sandbox flows — they don't know about DB or events. The services are the composable unit. The master graph is just a scheduler.

### (2) Shipwright gets a parallel-safety refactor + configurable concurrency

**Decision**: Phase 15 ships with **parallel Shipwright execution**, bounded by a user-configurable `max_concurrency`. The correctness dependency is a per-phase status gate on `Voyage.phase_status` (JSONB map: `{phase_number: "PENDING" | "BUILDING" | "BUILT" | "FAILED"}`). Shipwright refactors to gate on `phase_status[phase_number]` instead of `voyage.status`.

**Concurrency knob**:
- Storage: `DialConfig.role_mapping.shipwright.max_concurrency: int | None`. Default `1`, ceiling `10`. JSONB — no migration needed.
- Request override: `POST /voyages/{id}/start` accepts optional `max_parallel_shipwrights` for per-run tuning.
- Resolution order: request override → DialConfig value → default 1.

**Scheduling**: `building_node` runs phases in **topological layers** (dep-free phases → wait → phases whose deps just completed → wait → ...). Each layer uses `asyncio.Semaphore(max_concurrency)` + `asyncio.gather`. First failure cancels the remaining tasks in the layer; voyage → `FAILED`.

**Delete-before-insert scoping**: `ShipwrightService.build_code` changes its `BuildArtifact` deletion from `WHERE voyage_id = ?` to `WHERE voyage_id = ? AND phase_number = ?`. Matches the per-phase gate.

**Why**: Clock-time win (5-phase voyage goes from ~225s serial → ~75-90s at N=3). Zero token impact. User self-serves for their API plan — N=1 on free-tier keys, N=5+ on Enterprise.

**Log in decisions.md** (Phase 1): *"Shipwright gates on `Voyage.phase_status[phase_number]`, not `voyage.status`. `max_concurrency` lives in `DialConfig.role_mapping.shipwright`; default 1, ceiling 10. The pipeline schedules phases in topological layers bounded by a semaphore."*

### (3) Pause/resume via DB status flag; no LangGraph checkpointer

**Decision**: "Pause" sets `voyage.status = PAUSED`. The graph re-reads voyage status at the start of each stage node; if `PAUSED`, exits cleanly. Resume = re-invoke `POST /voyages/{id}/start`, which reads current status, sees which artifacts already exist, and picks up from the next stage (skip-already-satisfied-stages on resume).

**Why**: Product state is already in Postgres. LangGraph's checkpointer would duplicate it. Mid-stage pause is not supported — services are atomic units.

**Log in decisions.md**: *"Pipeline pause/resume is DB-status-driven and between-stage. Mid-service interruption is not supported in v1."*

### (4) SSE stream: forward existing Den Den Mushi events + add 5 pipeline-level events

**Decision**:
- Existing per-service events continue to be published unchanged.
- **Add** five pipeline-level events to `den_den_mushi/events.py`: `PipelineStartedEvent`, `PipelineStageEnteredEvent`, `PipelineStageCompletedEvent`, `PipelineCompletedEvent`, `PipelineFailedEvent`. Emitted by `PipelineService` around each stage transition.
- SSE endpoint (`GET /voyages/{id}/stream`) subscribes to the existing `stream_key(voyage_id)` with a fresh consumer name, forwards every event as `data: {json}\n\n`, closes when the voyage reaches a terminal status.

**Why**: Reuse the existing bus — one Redis stream per voyage. Real-time Observation Deck visibility for free.

### (5) VoyageStatus enum: reuse existing, do NOT add PARKED

**Decision**: All statuses needed by the state machine already exist. `PARKED` is dropped — `PAUSED` + `CANCELLED` cover the required UX.

**Why**: New enum values require migrations. Nothing in the pipeline actually needs `PARKED`; easy to add later if a real use case emerges.

### (6) Transition guards live in a centralized helper

**Decision**: New file `app/services/pipeline_guards.py` with one function per transition:
- `require_can_enter_planning(voyage)` — voyage.status in {CHARTED, PAUSED, FAILED}
- `require_can_enter_pdd(voyage, plan)` — plan exists
- `require_can_enter_tdd(voyage, poneglyphs)` — poneglyphs cover every planned phase
- `require_can_enter_building(voyage, health_checks)` — health_checks exist for every planned phase
- `require_can_enter_reviewing(voyage, build_artifacts)` — artifacts exist for every planned phase
- `require_can_enter_deploying(voyage, validation_run)` — most-recent validation_run.status == "passed"

Each raises `PipelineError(code, message)` on violation.

**Bonus**: guards also drive **skip-already-satisfied-stages** on resume — if artifacts exist, skip the stage + its LLM call. Token savings on re-run after a fix.

**Why**: Centralized, declarative, testable in isolation. One place to reason about invariants.

### (7) Services directly own final status, pipeline overrides for COMPLETED/FAILED

**Decision**: Each crew service still restores `voyage.status = CHARTED` on success/failure. The **pipeline** overrides after Helmsman returns: on success → `COMPLETED`, on any stage failure → `FAILED`. Helmsman's internal CHARTED-restore is harmless because the pipeline writes COMPLETED right after.

**Why**: Keeps services independently invokable (manual `POST /deploy` still works). Pipeline owns end-state because it's the only component that knows "we're done with the whole voyage, not just one stage".

## Service invocation reference

| Stage | Service call | Transient status | Scope |
|---|---|---|---|
| PLANNING | `CaptainService.chart_course(voyage, task)` | PLANNING | voyage |
| PDD | `NavigatorService.draft_poneglyphs(voyage, plan)` | PDD | voyage |
| TDD | `DoctorService.write_health_checks(voyage, poneglyphs, user_id)` | TDD | voyage |
| BUILDING | `ShipwrightService.build_code(voyage, phase_number)` × N (parallel, layer-scheduled) | `phase_status[phase] = BUILDING` | per-phase |
| REVIEWING | `DoctorService.validate_code(voyage, user_id, shipwright_files)` | REVIEWING | voyage |
| DEPLOYING | `HelmsmanService.deploy(voyage, tier="preview", user_id=...)` | DEPLOYING | voyage |

## Phases

### Phase 1: Shipwright parallel-safety refactor + `phase_status` + `max_concurrency`

**Produces**:
- `alembic/versions/<rev>_voyage_phase_status.py` — migration adding `Voyage.phase_status: JSONB` (default `{}`)
- `app/models/voyage.py` — add `phase_status: Mapped[dict[str, Any]]` column
- `app/services/shipwright_service.py` — refactor `build_code` to:
  - Gate on `voyage.phase_status.get(str(phase_number), "PENDING") in {"PENDING", "FAILED"}` instead of `voyage.status == CHARTED`
  - Transition `phase_status[phase_number] = "BUILDING"` at entry, `"BUILT"` on success, `"FAILED"` on exception
  - Remove the voyage-level `voyage.status` transition (voyage stays `CHARTED`; phase_status is the gate)
  - Scope `BuildArtifact` delete-before-insert to `(voyage_id, phase_number)`
  - New `ShipwrightError("PHASE_NOT_BUILDABLE")` for phase already in `BUILDING` or `BUILT`
- `app/schemas/dial_config.py` (or equivalent) — add optional `max_concurrency: int | None` (validated: `1 <= x <= 10`) to the `shipwright` role_mapping sub-schema
- Tests: update `tests/test_shipwright_service.py` + `tests/test_shipwright_api.py` for the new gate. Add new tests: two concurrent `build_code` calls on different phases succeed; two concurrent calls on the same phase → one wins, one gets 409. Add `tests/test_dial_config_schemas.py` for the `max_concurrency` validation.

**Depends on**: nothing (touches landed Phase 13 code — verify existing tests pass after refactor)

**Risk**: Medium-High — refactoring landed code. Careful test migration required.

**Prompt**: `pdd/prompts/features/pipeline/grandline-15-01-shipwright-parallel-safety.md`

**Key decisions locked here**:
- `phase_status` values: `"PENDING"`, `"BUILDING"`, `"BUILT"`, `"FAILED"`. No enum class (JSONB string); list them in a module-level constant for readability.
- `PHASE_NOT_BUILDABLE` → 409 at API (same precedent as voyage-not-CHARTED).
- Voyage.status stays `CHARTED` during per-phase builds. Only the pipeline will later wrap the BUILDING stage with a `voyage.status = BUILDING` transition.
- `max_concurrency` is **validated at schema level** (Pydantic Field with `ge=1, le=10`). If DialConfig JSONB contains an invalid value at read time, log a warning + fall back to 1.

### Phase 2: Transition guards + PipelineError

**Produces**:
- `app/services/pipeline_guards.py` — the six `require_can_enter_*` helpers + `PipelineError(code, message)` exception
- `tests/test_pipeline_guards.py` — one test class per guard covering happy path + each failure mode

**Depends on**: Phase 1 (guards reference `phase_status` for the "can enter reviewing" check — all phases must be `"BUILT"`)

**Risk**: Low — pure predicates over DB-loaded objects.

**Prompt**: `pdd/prompts/features/pipeline/grandline-15-02-guards.md`

### Phase 3: Master graph + PipelineService + pipeline events + parallel building_node

**Produces**:
- `app/crew/pipeline_graph.py` — master LangGraph `StateGraph` with `PipelineState` TypedDict. Nodes: `planning_node`, `pdd_node`, `tdd_node`, `building_node` (parallel inner scheduler over phases), `reviewing_node`, `deploying_node`, `finalize_node`. Linear edges + conditional routing to `pause_end` / `fail_end`.
- `app/services/pipeline_service.py` — `PipelineService` composing the five crew services. Methods: `start(voyage, user_id, deploy_tier="preview", max_parallel_shipwrights=None)`, `pause(voyage)`, `cancel(voyage)`, `get_status(voyage)` + `reader(session)`. Emits pipeline-level events. Writes a `VivreCard` at each stage transition.
- `app/den_den_mushi/events.py` — add 5 pipeline events + include in `AnyEvent` union
- `app/services/pipeline_service.py` includes the topological-layer scheduler:
  ```
  resolve max_concurrency (request → DialConfig → default 1)
  semaphore = asyncio.Semaphore(max_concurrency)
  layers = topological_layers(plan.phases)
  for layer in layers:
      await asyncio.gather(*[_build_with_semaphore(phase) for phase in layer])
  ```
  On any phase exception in a layer: cancel remaining tasks, re-raise.
- Tests: `tests/test_pipeline_graph.py` (mocked services, per-node happy + failure; pause-between-stages; full-graph smoke), `tests/test_pipeline_service.py` (status transitions, VivreCard writes, event publishing, final COMPLETED/FAILED override, resume from PAUSED, concurrency respects semaphore, dep ordering, skip-already-satisfied-stages), `tests/test_events.py` extended

**Depends on**: Phases 1 + 2

**Risk**: Medium-High — first cross-service composition + parallel scheduler + pause/resume semantics all in one prompt.

**Prompt**: `pdd/prompts/features/pipeline/grandline-15-03-graph-service.md`

**Design details locked here**:
- **PipelineState TypedDict**: `voyage_id`, `user_id`, `deploy_tier`, `max_parallel_shipwrights`, `task`, `plan`, `poneglyphs`, `health_checks`, `shipwright_files`, `validation_result`, `deployment`, `error`, `paused`.
- **Background runner**: `asyncio.create_task` on the running event loop (not FastAPI `BackgroundTasks`). The task opens its own `AsyncSession` via `async_session_factory()`. Task handle stored on `app.state.pipeline_tasks: dict[voyage_id, asyncio.Task]` for test introspection + future cancel support.
- **Pause check**: at the top of every stage node, re-read voyage from DB, check `voyage.status == PAUSED`, route to `pause_end`.
- **Error translation**: catch each service's `<Agent>Error`, set `state["error"] = {"code", "message", "stage"}`, route to `fail_end` → `finalize_node` sets `voyage.status = FAILED` + publishes `PipelineFailedEvent`.
- **Parallel scheduler**: `topological_layers(phases) -> list[list[int]]` is a helper. Returns `[[1, 2], [3], [4, 5]]` style layers. Inside `building_node`, per layer: `asyncio.gather(*[build_one(p) for p in layer])`. Semaphore bounds total concurrent calls across all layers.
- **Skip-already-satisfied**: each stage node first checks if its output artifacts exist. If yes, skip to next stage (no service call, no LLM call). Token savings on resume.
- **Concurrency resolution**: read from `DialConfig.role_mapping.shipwright.max_concurrency`. Fall back to 1 if absent/invalid. Request `max_parallel_shipwrights` overrides.

### Phase 4: REST + SSE endpoints

**Produces**:
- `app/api/v1/pipeline.py` — `POST /voyages/{id}/start`, `POST /voyages/{id}/pause`, `POST /voyages/{id}/cancel`, `GET /voyages/{id}/status`, `GET /voyages/{id}/stream` (SSE)
- `app/api/v1/router.py` — include router
- `app/schemas/pipeline.py` — `StartVoyageRequest` (with optional `max_parallel_shipwrights: int | None` validated `1 <= x <= 10`, optional `deploy_tier: Literal["preview"]` defaulting to `"preview"`), `VoyageStatusResponse`, `PipelineEventEnvelope`
- `app/api/v1/dependencies.py` — `get_pipeline_service` + `get_pipeline_service_reader`
- Tests: `tests/test_pipeline_api.py` — full endpoint matrix + SSE streaming test with httpx streaming client

**Depends on**: Phase 3

**Risk**: Medium — SSE semantics + background-task scheduling test hygiene.

**Prompt**: `pdd/prompts/features/pipeline/grandline-15-04-api-sse.md`

**Design details locked here**:
- **SSE format**: `data: {json}\n\n`. No named events.
- **SSE consumer lifecycle**: fresh consumer per connection (`f"sse-{uuid.uuid4().hex}"`). Short block timeout (~1s) with disconnect check each loop.
- **SSE termination**: poll `voyage.status`; close on terminal (`COMPLETED` | `FAILED` | `CANCELLED`).
- **POST /start**: accepts optional `max_parallel_shipwrights`. Idempotency: running stage → 409; COMPLETED → 409 (use `/cancel` + re-run out of scope for v1); PAUSED / CHARTED / FAILED → accept.
- **Status response**: `{status, plan_exists, poneglyph_count, health_check_count, build_artifact_count, phase_status, last_validation, last_deployment, error}`.

### Phase 5: End-to-end integration test

**Produces**:
- `tests/test_pipeline_integration.py` — full pipeline test:
  - Real Postgres + Redis (existing fixtures)
  - Mocked `DialSystemRouter.route` with a role-keyed response helper (maps `CrewRole → pre-canned JSON`)
  - Real `InProcessDeploymentBackend` + `DockerExecutionBackend` (test fixture seeds it with a passing pytest fixture)
  - Top-level assertions: voyage reaches `COMPLETED`, all artifacts exist, event sequence on Redis stream is correct
- Failure-path tests:
  - Doctor validate returns failed → voyage `FAILED`, no Deployment row
  - Helmsman deploy fails → voyage `FAILED` with diagnosis in Deployment
  - Parallel Shipwright respects `max_concurrency=2` (patch Semaphore, assert no more than 2 concurrent enters)
  - Dep ordering respected (phase 3 depending on phase 1+2 doesn't start before both complete)
  - Resume skips already-satisfied stages (pre-seed Poneglyphs, run pipeline, assert Captain+Navigator not called)

**Depends on**: Phases 1-4

**Risk**: Medium-High — first full-path test through real Postgres + Redis for this pipeline. Fixture churn expected.

**Prompt**: `pdd/prompts/features/pipeline/grandline-15-05-integration.md`

## Risks & Unknowns

- **Shipwright refactor regression risk**: Phase 1 touches landed Phase 13 code. Every existing Shipwright test must be re-reasoned against the new `phase_status` semantics. Mitigation: run full suite after Phase 1 before starting Phase 2.

- **Background task lifecycle**: `asyncio.create_task` without shutdown coordination leaks if the app shuts down mid-voyage. V1 acceptable — voyage resumes via `POST /start` on next run. Track tasks on `app.state.pipeline_tasks`.

- **Session per background task**: spawned task opens its own `AsyncSession` via `async_session_factory`. The request's session is closed when the response returns.

- **Parallel rate-limit blowups**: a user mis-configures `max_concurrency=10` on a free-tier key. Mitigation: Dial System's existing fallback_chain handles 429s per-adapter. Document the risk; let the user self-serve the knob.

- **Dep-graph correctness**: topological layers assume the plan's deps are acyclic. Captain validates this; if somehow a bad plan leaks through, the layer scheduler deadlocks (never produces layer 2). Mitigation: `topological_layers` raises `PipelineError("INVALID_DEP_GRAPH")` on cycle detection.

- **Fail-fast vs fail-slow in parallel builds**: one phase fails in a layer — do we cancel running tasks or let them finish? Decision: **cancel** (fail-fast). Rationale: the voyage is going to `FAILED` anyway; wasted LLM tokens on in-flight phases are a pure loss. Semaphore release on cancel is handled by `asyncio`.

- **LLM cost for integration test**: fully mocked via `DialSystemRouter.route` patch. Role-keyed helper returns canned JSON per `CrewRole`.

- **Resume-skips-satisfied vs "I want to force re-run"**: v1 skip is aggressive — if Poneglyphs exist, never re-draft. Force re-run = `POST /cancel` (status → CANCELLED), then... ? Deferred. Log as scope cut.

- **SSE client disconnect detection**: short block timeout with disconnect check each loop.

## Decisions Needed (none — all resolved)

All seven design decisions locked. Scope cuts accepted:
- ✅ `PARKED` dropped (reuse existing enum)
- ✅ No mid-stage pause
- ✅ No forcible restart from CANCELLED in v1
- ✅ Preview tier only for pipeline deploys
- ✅ Skip-already-satisfied-stages on resume
- ✅ Parallel Shipwright with configurable concurrency (1-10, default 1)
- ✅ Fail-fast on parallel phase failure
- ✅ `DialConfig.role_mapping.shipwright.max_concurrency` as storage; request override allowed

## Next step

Run `/pdd-prompts` for Phase 1 → produce `pdd/prompts/features/pipeline/grandline-15-01-shipwright-parallel-safety.md`. Implement TDD-first, review, commit. Then iterate through Phases 2-5.
