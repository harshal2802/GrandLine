# Phase 15.3: Master Pipeline Graph + PipelineService + Pipeline Events + Parallel Building

## Context

Phase 15 wires the five crew agents (Captain → Navigator → Doctor → Shipwright ×
N → Doctor → Helmsman) into a single master LangGraph with a formal state
machine. Phase 15.1 landed parallel-safe Shipwright (per-phase `phase_status`
gate, configurable concurrency). Phase 15.2 landed six pure-predicate
transition guards in `app/services/pipeline_guards.py`. This phase is the
**composition layer**: the master graph, the orchestrating service, the
pipeline-level event types, the parallel scheduler with topological layering,
and pause/resume semantics — all built on top of the five already-landed crew
services.

The master graph is a **thin scheduler**. Each stage node re-reads the voyage
from DB, checks the matching guard from Phase 15.2, dispatches to the
corresponding crew service, translates failures into a `FAILED` voyage, and
emits pipeline-level events. The nodes do NOT duplicate DB writes, VivreCard
checkpointing, or per-service event publishing — the crew services already
own all of that (see
[helmsman_service.py:289-344](src/backend/app/services/helmsman_service.py#L289-L344)
and the equivalent in captain/navigator/doctor/shipwright). The pipeline
adds only what's new: cross-stage orchestration, parallel Shipwright
scheduling, and lifecycle events around each stage transition.

No REST or SSE endpoints in this phase — Phase 15.4 will wire
`POST /voyages/{id}/start`, `GET /voyages/{id}/status`, and
`GET /voyages/{id}/stream`. No end-to-end integration test — Phase 15.5 will
add that. This phase is unit-tested with mocked crew services.

**Locked decisions driving this phase** (see
[PLAN-voyage-pipeline.md](PLAN-voyage-pipeline.md)):

- **Graph invokes services directly, not sub-graphs.** Each node is an async
  wrapper around `CaptainService.chart_course(...)` /
  `NavigatorService.draft_poneglyphs(...)` / etc. The crew sub-graphs own
  LLM flows; the crew services own DB writes + events + checkpoints. The
  master graph is just a scheduler.
- **Master graph state** — a `PipelineState` TypedDict carries `voyage_id`,
  `user_id`, `deploy_tier`, `max_parallel_shipwrights`, `task`, `plan`,
  `poneglyphs`, `health_checks`, `shipwright_files`, `validation_result`,
  `deployment`, `error`, `paused`. The graph does NOT hold DB objects
  across node boundaries — each node re-reads from DB via its own session
  adapter if needed.
- **Parallel Shipwright** — `building_node` computes topological layers
  from the plan's `depends_on` graph, runs each layer via
  `asyncio.gather` bounded by an `asyncio.Semaphore(max_concurrency)`.
  First failure in a layer cancels the rest of the layer; voyage →
  `FAILED`. Resolution order for `max_concurrency`:
  request override → `DialConfig.role_mapping.shipwright.max_concurrency`
  → default `1`. Already-landed helper
  [resolve_shipwright_max_concurrency](src/backend/app/schemas/dial_config.py#L39-L57)
  handles the DialConfig read.
- **Skip-already-satisfied-stages on resume** — each stage node checks its
  output artifacts first. If they satisfy the *next* guard, the node returns
  immediately with no service call. No LLM tokens, no DB writes. This is
  what makes resume cheap after a fix.
- **Pause is between-stage only** — each stage node re-reads
  `voyage.status` at entry. If `PAUSED`, routes to `pause_end` and the
  graph terminates cleanly. Mid-stage pause is not supported; services
  are atomic. Resume = re-invoke start; guards + skip-already-satisfied
  pick up from the next unsatisfied stage.
- **Pipeline owns COMPLETED and FAILED** — each crew service still restores
  `voyage.status = CHARTED` on success (existing behavior). The pipeline
  overrides after finalize: success → `COMPLETED`, any stage failure →
  `FAILED`. Helmsman's internal CHARTED-restore is harmless because
  `finalize_node` writes `COMPLETED` immediately after.
- **Five pipeline-level events** — `PipelineStartedEvent`,
  `PipelineStageEnteredEvent`, `PipelineStageCompletedEvent`,
  `PipelineCompletedEvent`, `PipelineFailedEvent`. Added to
  `app/den_den_mushi/events.py` and included in the `AnyEvent` union.
  Published best-effort via the same pattern as existing crew events
  ([helmsman_service.py:289-344](src/backend/app/services/helmsman_service.py#L289-L344)).
- **VivreCard checkpoints per stage transition** — `PipelineService`
  writes a `VivreCard` (crew_member=`"pipeline"`, reason=
  `"stage_entered"` / `"stage_completed"`) at each transition. State_data
  captures the stage name + condensed snapshot (phase counts, not full
  content). This augments per-service VivreCards, doesn't replace them.
- **Background task runner is out of scope for this phase** — the service
  exposes an `async def start(...)` method that runs the graph to
  completion in the caller's event loop. Phase 15.4 will add the
  `asyncio.create_task` wrapping + `app.state.pipeline_tasks` registry
  at the API layer. Keeping the service sync-to-completion here makes
  it straightforward to test without a running event loop harness.

## Deliverables

### 1. Pipeline events: `app/den_den_mushi/events.py`

**Add five classes** following the existing `DenDenMushiEvent` base pattern
(see [events.py:12-20](src/backend/app/den_den_mushi/events.py#L12-L20)):

| Class | `event_type` literal | `source_role` | Payload fields |
|---|---|---|---|
| `PipelineStartedEvent` | `"pipeline_started"` | `"captain"` | `task: str`, `deploy_tier: str`, `max_parallel_shipwrights: int` |
| `PipelineStageEnteredEvent` | `"pipeline_stage_entered"` | `"captain"` | `stage: str` (PLANNING/PDD/TDD/BUILDING/REVIEWING/DEPLOYING), `voyage_status: str` |
| `PipelineStageCompletedEvent` | `"pipeline_stage_completed"` | `"captain"` | `stage: str`, `duration_seconds: float`, `skipped: bool` |
| `PipelineCompletedEvent` | `"pipeline_completed"` | `"captain"` | `duration_seconds: float`, `deployment_url: str \| None` |
| `PipelineFailedEvent` | `"pipeline_failed"` | `"captain"` | `stage: str`, `code: str`, `message: str` |

**`source_role`**: pipeline events don't map cleanly to one crew role, but
the existing enum lacks a "pipeline" value. Use `CrewRole.CAPTAIN` as the
source (the Captain orchestrates the voyage). Document this in a one-line
comment on each event class.

**Add all five to the `AnyEvent` discriminated union** at
[events.py:71-85](src/backend/app/den_den_mushi/events.py#L71-L85).
Maintain alphabetical order if the existing union uses it, else append.

### 2. Master graph: `app/crew/pipeline_graph.py`

**`PipelineState` TypedDict** — carries state across stage nodes:

```python
class PipelineState(TypedDict, total=False):
    # Inputs (always present)
    voyage_id: uuid.UUID
    user_id: uuid.UUID
    deploy_tier: Literal["preview"]
    max_parallel_shipwrights: int
    task: str

    # Accumulated artifacts (populated as stages complete)
    plan: dict[str, Any] | None            # VoyagePlan.phases dict
    poneglyph_ids: list[uuid.UUID]
    health_check_ids: list[uuid.UUID]
    build_artifact_ids: list[uuid.UUID]
    shipwright_files: dict[str, str]        # {file_path: content}, for Doctor validate
    validation_run_id: uuid.UUID | None
    deployment_id: uuid.UUID | None

    # Control flow
    error: dict[str, Any] | None            # {"code", "message", "stage"}
    paused: bool
```

Only primitive / id values — no ORM objects. Each node loads what it needs
via its own session.

**Nodes** (one async function per stage):

| Node | Service call | Guard called before |
|---|---|---|
| `planning_node` | `CaptainService.chart_course(voyage, task)` | `require_can_enter_planning` |
| `pdd_node` | `NavigatorService.draft_poneglyphs(voyage, plan)` | `require_can_enter_pdd` |
| `tdd_node` | `DoctorService.write_health_checks(voyage, poneglyphs, user_id)` | `require_can_enter_tdd` |
| `building_node` | `ShipwrightService.build_code(voyage, phase, poneglyph, health_checks, user_id)` × N phases (topological-layer parallel) | `require_can_enter_building` |
| `reviewing_node` | `DoctorService.validate_code(voyage, user_id, shipwright_files)` | `require_can_enter_reviewing` |
| `deploying_node` | `HelmsmanService.deploy(voyage, tier, user_id, git_ref=None)` | `require_can_enter_deploying` |
| `finalize_node` | — writes `voyage.status = COMPLETED`, emits `PipelineCompletedEvent` | none |
| `pause_end` | — terminal no-op | none |
| `fail_end` | — writes `voyage.status = FAILED`, emits `PipelineFailedEvent` | none |

**Each stage node responsibility**:
1. Re-read voyage from DB. If `voyage.status == PAUSED`, set
   `state["paused"] = True`, route to `pause_end`.
2. Call the matching guard from `app.services.pipeline_guards`. If the
   guard passes BUT the stage's output already exists (skip-already-
   satisfied check — see below), set `skipped = True` and emit a
   `PipelineStageCompletedEvent` with `skipped=True`, then return.
3. If the guard raises `PipelineError`, and the **previous** stage's
   output is what's missing (i.e. this is a dependency failure from an
   aborted prior run), re-raise unchanged → routes to `fail_end`.
4. Otherwise, emit `PipelineStageEnteredEvent`, record start timestamp,
   call the crew service, emit `PipelineStageCompletedEvent` with
   `duration_seconds` on success.
5. On crew-service error (any `<Agent>Error` subclass), set
   `state["error"] = {"code", "message", "stage"}`, route to `fail_end`.

**Skip-already-satisfied logic** — each stage first checks whether its
output artifacts fully satisfy the *next* guard. If yes, the stage is
skipped (no service call). Rules:

- `planning_node`: skip if `plan` already exists for the voyage.
- `pdd_node`: skip if `require_can_enter_tdd(voyage, plan, poneglyphs)`
  passes (every planned phase has ≥1 poneglyph).
- `tdd_node`: skip if `require_can_enter_building(voyage, plan,
  health_checks)` passes.
- `building_node`: skip if `require_can_enter_reviewing(voyage, plan,
  build_artifacts)` passes (all phases BUILT with artifacts). On partial
  skip, only build the missing phases.
- `reviewing_node`: skip if latest `ValidationRun.status == "passed"`.
- `deploying_node`: never skip; deploying is always the last step and
  re-deploying is a user-driven action, not an automatic skip.

**Edges**:
- `START → planning_node`
- `planning_node → pdd_node → tdd_node → building_node → reviewing_node → deploying_node → finalize_node → END`
- Conditional from every stage node: `state["paused"] is True` →
  `pause_end → END`; `state["error"] is not None` → `fail_end → END`.

**`compile_pipeline_graph() -> CompiledStateGraph`** — factory function
returning the compiled graph. Matches the convention in other
`app/crew/*.py` files ([helmsman_graph.py:47-59](src/backend/app/crew/helmsman_graph.py#L47-L59)
for the TypedDict pattern and compile semantics).

**Parallel scheduling inside `building_node`**:

```python
async def building_node(state: PipelineState) -> PipelineState:
    # ... guard check + skip-already-satisfied ...
    layers = topological_layers(plan.phases)           # helper, new
    semaphore = asyncio.Semaphore(max_parallel_shipwrights)
    for layer in layers:
        # Filter out already-built phases (partial resume support)
        pending = [p for p in layer if phase_status.get(str(p)) != "BUILT"]
        tasks = [_build_one(phase, semaphore, ...) for phase in pending]
        try:
            await asyncio.gather(*tasks)
        except Exception:
            # Cancel remaining, re-raise (fail-fast)
            for t in tasks:
                if not t.done():
                    t.cancel()
            raise
    return state
```

**`topological_layers(phases: list[PhaseSpec]) -> list[list[int]]`** —
helper in the same module. Returns dep-free phases first, then phases
whose deps are in prior layers, etc. On cycle detection, raise
`PipelineError("INVALID_DEP_GRAPH", ...)`. Captain's
[VoyagePlanSpec.validate_plan_graph](src/backend/app/schemas/captain.py#L23)
already prevents cycles at write time, so this is defense-in-depth.

### 3. Orchestrator: `app/services/pipeline_service.py`

**`PipelineService` class** — exposes the lifecycle operations the API
will bind to. Follows the same shape as existing crew services:

```python
class PipelineService:
    def __init__(
        self,
        session: AsyncSession,
        mushi: DenDenMushi,
        dial_router: DialSystemRouter,
        execution_service: ExecutionService,
        git_service: GitService | None,
        deployment_backend: DeploymentBackend,
    ) -> None: ...

    @classmethod
    def reader(cls, session: AsyncSession) -> "PipelineService": ...

    async def start(
        self,
        voyage: Voyage,
        user_id: uuid.UUID,
        deploy_tier: Literal["preview"] = "preview",
        max_parallel_shipwrights: int | None = None,
    ) -> None: ...

    async def pause(self, voyage: Voyage) -> None: ...
    async def cancel(self, voyage: Voyage) -> None: ...

    async def get_status(self, voyage: Voyage) -> PipelineStatusSnapshot: ...
```

**`reader` factory** builds a read-only variant with `mushi=None`,
`dial_router=None`, etc. — used by the `GET /status` endpoint in Phase
15.4. Mirrors the pattern from
[shipwright_service.py:73](src/backend/app/services/shipwright_service.py#L73)
and [helmsman_service.py:89](src/backend/app/services/helmsman_service.py#L89).

**`start()` responsibilities**:
1. Resolve `max_concurrency`: request override → DialConfig value (via
   [resolve_shipwright_max_concurrency](src/backend/app/schemas/dial_config.py#L39-L57))
   → default `1`.
2. Call `require_can_enter_planning(voyage)`. If it raises, wrap in
   `PipelineError` with stage=`"planning"` and re-raise.
3. Emit `PipelineStartedEvent`.
4. Build the initial `PipelineState`, compile the graph, run to
   completion via `graph.ainvoke(initial_state)`.
5. Status transitions: at graph entry, set
   `voyage.status = PLANNING`. Each node updates to the matching status
   before emitting `PipelineStageEnteredEvent`. `finalize_node` writes
   `COMPLETED`; `fail_end` writes `FAILED`; `pause_end` leaves the
   voyage as `PAUSED`.
6. On any exception escaping the graph, set `voyage.status = FAILED`,
   emit `PipelineFailedEvent`, re-raise as `PipelineError`.

**`pause()`** — sets `voyage.status = PAUSED`, commits, emits no event
(the graph's next stage transition will detect PAUSED and route to
`pause_end`; that's where the observable "paused" signal lives).

**`cancel()`** — sets `voyage.status = CANCELLED`, commits. Like pause,
the next stage node observes the state change and exits. Unlike pause,
cancel is terminal.

**`get_status()`** — returns a `PipelineStatusSnapshot` (new schema, see
below). Pure read, no commit. Aggregates: voyage.status, plan presence,
poneglyph count, health_check count, build_artifact count + phase_status
map, latest validation result, latest deployment, last error if any.

**`PipelineStatusSnapshot`** lives in a new `app/schemas/pipeline.py`
module (even though Phase 15.4 is the main schema phase — the
orchestrator's return type is needed now for testing):

```python
class PipelineStatusSnapshot(BaseModel):
    model_config = ConfigDict(strict=True)
    voyage_id: uuid.UUID
    status: str
    plan_exists: bool
    poneglyph_count: int
    health_check_count: int
    build_artifact_count: int
    phase_status: dict[str, str]
    last_validation_status: str | None
    last_deployment_status: str | None
    error: dict[str, Any] | None
```

**VivreCard checkpoints** — write at each stage transition:

```python
VivreCard(
    voyage_id=voyage.id,
    crew_member="pipeline",
    state_data={"stage": stage, "phase_status": voyage.phase_status, ...},
    checkpoint_reason="stage_entered",  # or "stage_completed"
)
```

Match the existing write pattern from
[captain_service.py:103-113](src/backend/app/services/captain_service.py#L103-L113).

**Error handling**:
- Any crew error (`CaptainError`, `NavigatorError`, `DoctorError`,
  `ShipwrightError`, `HelmsmanError`) → translate to `PipelineError(code,
  message)` with the stage appended to `message`.
- Any `PipelineError` from a guard → re-raise unchanged.
- Any other exception → wrap as `PipelineError("PIPELINE_INTERNAL", str(e))`.
- All paths emit `PipelineFailedEvent` before re-raising.

### 4. No API endpoints, no background task wiring in this phase

- Do NOT touch `app/api/v1/router.py` or create `app/api/v1/pipeline.py`
  — Phase 15.4 owns that.
- Do NOT modify `app/api/v1/dependencies.py` — Phase 15.4 owns it.
- Do NOT modify `app/main.py` lifespan.
- `PipelineService` is **not** registered anywhere yet. Tests construct
  it directly.

### 5. Tests

**`tests/test_events.py`** (extend existing file or create if absent):
- `test_pipeline_started_event_shape`
- `test_pipeline_stage_entered_event_shape`
- `test_pipeline_stage_completed_event_shape`
- `test_pipeline_completed_event_shape`
- `test_pipeline_failed_event_shape`
- `test_any_event_discriminates_pipeline_started_by_type`
- `test_any_event_discriminates_pipeline_failed_by_type`

Check the existing file first; if the pattern is to have one test per
event, follow it. Model shape assertions on `event_type`, required
payload keys, `source_role`.

**`tests/test_pipeline_graph.py`** (new):

- `TestTopologicalLayers`:
  - `test_single_phase_one_layer`
  - `test_independent_phases_one_layer`
  - `test_linear_chain_n_layers` — phase 1 → 2 → 3 → three layers
  - `test_diamond_two_layers` — 1, 2 independent; 3 depends on [1, 2]
  - `test_cycle_raises_invalid_dep_graph` — although Captain prevents
    this, defense-in-depth test that the helper itself raises

- `TestPlanningNode`:
  - `test_happy_path_calls_service_and_writes_plan`
  - `test_skip_when_plan_exists`
  - `test_routes_to_pause_end_when_voyage_paused`
  - `test_routes_to_fail_end_on_captain_error`
  - `test_routes_to_fail_end_on_guard_failure`

- `TestPddNode`, `TestTddNode`, `TestReviewingNode`, `TestDeployingNode`:
  same 5 cases each, swapping the service and the guard.

- `TestBuildingNode`:
  - `test_single_layer_all_phases_parallel` — plan has 3 indep phases,
    assert `ShipwrightService.build_code` called 3 times
  - `test_two_layers_respects_order` — plan has phase 1, then 2 depending
    on 1; assert phase 1's call resolves before phase 2's starts (mock
    service with `asyncio.Event` coordination to enforce observation)
  - `test_semaphore_bounds_concurrency` — 5 indep phases, max=2; patch
    `asyncio.Semaphore` to assert at most 2 concurrent enters
  - `test_partial_resume_skips_already_built_phases` — phase_status[1]=
    "BUILT", phase_status[2]="PENDING" → only phase 2 is built
  - `test_first_failure_cancels_layer_and_routes_to_fail_end`
  - `test_routes_to_pause_end_when_voyage_paused_mid_build` — only
    between layers (mid-layer pause not supported)

- `TestFinalizeAndFailEnd`:
  - `test_finalize_sets_completed_and_emits_event`
  - `test_fail_end_sets_failed_and_emits_event`
  - `test_pause_end_leaves_voyage_paused`

- `TestFullGraphSmoke`:
  - `test_charted_voyage_runs_to_completed` — all services mocked with
    happy-path returns, assert terminal status = COMPLETED
  - `test_pipeline_failure_in_tdd_sets_failed_and_skips_later_stages`
  - `test_all_stages_skipped_on_fully_satisfied_voyage` — pre-seed all
    artifacts; voyage runs to COMPLETED with 0 crew service calls

**`tests/test_pipeline_service.py`** (new):

- `TestPipelineServiceInit`:
  - `test_init_stores_all_deps`
  - `test_reader_classmethod_returns_read_only_instance`

- `TestStart`:
  - `test_happy_path_writes_completed_and_emits_completed_event`
  - `test_writes_pipeline_started_event_at_entry`
  - `test_writes_vivre_card_at_each_stage_transition`
  - `test_raises_pipeline_error_when_voyage_not_plannable`
  - `test_resolves_max_concurrency_from_request_override`
  - `test_resolves_max_concurrency_from_dial_config_when_no_override`
  - `test_defaults_max_concurrency_to_one_when_neither_set`
  - `test_crew_error_translates_to_pipeline_error_with_stage`
  - `test_emits_pipeline_failed_on_any_failure_path`

- `TestPause`:
  - `test_sets_voyage_status_paused_and_commits`
  - `test_pause_is_idempotent_on_already_paused_voyage`

- `TestCancel`:
  - `test_sets_voyage_status_cancelled_and_commits`
  - `test_cancel_is_idempotent_on_terminal_voyage` — CANCELLED,
    COMPLETED, FAILED all no-op

- `TestGetStatus`:
  - `test_returns_snapshot_with_all_counts`
  - `test_snapshot_includes_phase_status_map`
  - `test_snapshot_last_error_captures_most_recent_failure`

- `TestResumeFromPaused`:
  - `test_resume_from_paused_picks_up_from_next_unsatisfied_stage` —
    pre-seed plan + poneglyphs + health_checks; voyage status PAUSED.
    Call start(); assert Captain NOT called, Navigator NOT called,
    Doctor (write) NOT called, Shipwright IS called.

**Test fixtures**:
- Mock all five crew services with `AsyncMock`. Patch the `reader`
  classmethod to return the mock.
- Mock `DialSystemRouter`, `ExecutionService`, `GitService`,
  `DeploymentBackend` — none are invoked directly by the pipeline
  service; they're passed through to crew service constructors.
- Mock `DenDenMushi.publish` as `AsyncMock`; assert call args for event
  verification.
- Voyages, plans, poneglyphs, health_checks, build_artifacts — use
  `MagicMock` with `phase_status` as a real dict (same pattern as
  [test_pipeline_guards.py](src/backend/tests/test_pipeline_guards.py)).
- For full-graph smoke tests, use the real compiled graph with mocked
  service factories — don't mock the graph itself.
- Do NOT require Postgres or Redis; this phase is all unit tests with
  mocks. Phase 15.5 is the real-infra integration test.

## Test Plan

- [ ] All new tests in `tests/test_pipeline_graph.py` and
  `tests/test_pipeline_service.py` pass
- [ ] New event tests in `tests/test_events.py` pass
- [ ] All 666 existing tests still pass (this phase adds code; does
  NOT modify existing code paths)
- [ ] `ruff check app/ tests/` clean
- [ ] `mypy app/` clean
- [ ] `TestTopologicalLayers.test_cycle_raises_invalid_dep_graph`
  passes with `PipelineError("INVALID_DEP_GRAPH", ...)`
- [ ] `test_semaphore_bounds_concurrency` verifies max-2 with 5 phases
  (no 3+ concurrent build_code calls)
- [ ] `test_partial_resume_skips_already_built_phases` verifies phase-1-BUILT
  + phase-2-PENDING → only phase 2 rebuilt
- [ ] Skip-already-satisfied logic covered for every stage except
  `deploying_node`
- [ ] `test_routes_to_pause_end_when_voyage_paused` covered for every
  stage node
- [ ] `test_all_stages_skipped_on_fully_satisfied_voyage` confirms
  zero crew-service calls on a pre-seeded voyage
- [ ] Log one decision to
  [pdd/context/decisions.md](pdd/context/decisions.md) (see Constraints)

## Constraints

- **Scheduler-only graph** — nodes do not duplicate DB writes, event
  publishing, or VivreCard writes the crew services already perform.
  Add only pipeline-level events and stage-transition checkpoints.
- **Do NOT add background task scheduling** — no `asyncio.create_task`
  in `PipelineService`. Phase 15.4 owns the API layer that spawns the
  task. `PipelineService.start()` runs synchronously to graph
  completion in the caller's loop.
- **Do NOT add REST or SSE** — Phase 15.4.
- **Do NOT add end-to-end integration tests** — Phase 15.5. This phase
  is unit tests with mocked services.
- **Do NOT modify existing crew service signatures or error codes** —
  they're stable and landed. Compose them as-is.
- **Parallel Shipwright uses `asyncio.Semaphore` + `asyncio.gather`**,
  not a custom queue. Standard-library idioms only.
- **Topological layers, not DAG traversal** — `[[1, 2], [3], [4, 5]]`
  style. `asyncio.gather` per layer. First exception in a layer
  cancels the remaining tasks in that layer.
- **Fail-fast on parallel failure** — cancel remaining tasks, re-raise.
  Do not wait for in-flight to finish; the voyage is headed to FAILED
  either way.
- **No LangGraph checkpointers** — pause/resume is DB-status-driven.
- **Skip-already-satisfied is aggressive** — if artifacts exist, never
  re-run. Force-regenerate is out of scope (cancel + restart is the
  workaround).
- **`max_parallel_shipwrights` resolution order**: request override →
  DialConfig → default `1`. Validate `1 <= x <= 10` at entry (reuse
  existing Pydantic Field constraint from
  [dial_config.py:ShipwrightRoleConfig](src/backend/app/schemas/dial_config.py#L15-L24)).
- **Error propagation**: every crew error translates to a single
  `PipelineError(code, message)` — preserve the original code, append
  stage name to message. Mirrors Phase 15.2's
  [PipelineError](src/backend/app/services/pipeline_guards.py#L28-L34).
- **`source_role` on pipeline events**: `CrewRole.CAPTAIN` (the
  existing enum lacks a PIPELINE value; adding it would require an
  enum migration we don't need here). Document in an inline comment.
- **Event publishing is best-effort** — each publish in its own
  try/except; warn on failure. Same pattern as
  [helmsman_service.py:289-344](src/backend/app/services/helmsman_service.py#L289-L344).
- **`PipelineStatusSnapshot` goes in `app/schemas/pipeline.py`** —
  create this module now even though Phase 15.4 is the "schemas phase".
  The service's return type needs it.
- **Log one decision** to
  [pdd/context/decisions.md](pdd/context/decisions.md). Suggested text:
  *"Phase 15.3 (2026-04-20): Master pipeline graph invokes crew
  services directly (not sub-graphs). PipelineService composes the
  five crew services, adds 5 pipeline-level events, writes VivreCard
  checkpoints at each stage transition, and runs parallel Shipwright
  phases in topological layers bounded by
  `asyncio.Semaphore(max_concurrency)`. Skip-already-satisfied-stages
  on resume uses the Phase 15.2 guards — if a guard passes, the stage
  is skipped with no service / LLM call. Pause/resume is DB-status-
  driven and between-stage only. Background task spawning lives at the
  API layer (Phase 15.4), not here."*
- **No commit or PR until the user signs off.**

## References

- Plan: [pdd/prompts/features/pipeline/PLAN-voyage-pipeline.md](PLAN-voyage-pipeline.md)
- Phase 15.1: [PR #35](https://github.com/harshal2802/GrandLine/pull/35) —
  `Voyage.phase_status`, `resolve_shipwright_max_concurrency`,
  `ShipwrightError("PHASE_NOT_BUILDABLE")`
- Phase 15.2: [PR #36](https://github.com/harshal2802/GrandLine/pull/36) —
  `app/services/pipeline_guards.py`, `PipelineError`
- Crew services (all have the `reader(session)` factory + per-service
  error class + best-effort event publishing):
  - [captain_service.py](src/backend/app/services/captain_service.py) —
    `chart_course(voyage, task)`
  - [navigator_service.py](src/backend/app/services/navigator_service.py) —
    `draft_poneglyphs(voyage, plan)`
  - [doctor_service.py](src/backend/app/services/doctor_service.py) —
    `write_health_checks(voyage, poneglyphs, user_id)` +
    `validate_code(voyage, user_id, shipwright_files)`
  - [shipwright_service.py](src/backend/app/services/shipwright_service.py) —
    `build_code(voyage, phase_number, poneglyph, health_checks, user_id)`
  - [helmsman_service.py](src/backend/app/services/helmsman_service.py) —
    `deploy(voyage, tier, user_id, git_ref=None, approved_by=None)`
- Crew graph convention:
  [helmsman_graph.py](src/backend/app/crew/helmsman_graph.py) —
  TypedDict state + `compile_*_graph()` factory
- Event base + discriminated union:
  [events.py](src/backend/app/den_den_mushi/events.py)
- VivreCard shape: [vivre_card.py](src/backend/app/models/vivre_card.py)
- Voyage model (with `phase_status`):
  [voyage.py](src/backend/app/models/voyage.py)
- VoyagePlanSpec / PhaseSpec:
  [schemas/captain.py](src/backend/app/schemas/captain.py)
- DialConfig resolver:
  [schemas/dial_config.py:39-57](src/backend/app/schemas/dial_config.py#L39-L57)
- Guards (consumers of this phase):
  [services/pipeline_guards.py](src/backend/app/services/pipeline_guards.py)
