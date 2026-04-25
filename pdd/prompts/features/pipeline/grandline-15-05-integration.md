# Phase 15.5: End-to-end Voyage Pipeline Integration Test

## Context

Phases 15.1–15.4 are landed:
- **15.1** parallel-safe Shipwright + `phase_status` gate + `max_concurrency`
- **15.2** transition guards + `PipelineError`
- **15.3** master `pipeline_graph` + `PipelineService` + 5 pipeline events
- **15.4** REST + SSE API surface

Every layer has unit tests. What's still missing — and what this final phase
provides — is a **single full-path test** that exercises the whole pipeline
end-to-end against real Postgres + Redis with **only the LLM boundary
mocked**. This catches anything that slips through the unit layer:
session lifecycle bugs, Redis stream ordering issues, dep-graph scheduling
under real `asyncio.gather`, transaction visibility across the
background-task / request boundary, and skip-already-satisfied resume on
real persisted state.

After this phase the Voyage Pipeline (Phase 15) is **feature-complete**.
The only Phase-15 work that remains afterwards is whatever the integration
test discovers — bug fixes go in follow-up PRs.

**Locked decisions driving this phase** (see
[PLAN-voyage-pipeline.md](PLAN-voyage-pipeline.md) §Phase 5):

- **Real Postgres + Redis, mocked LLM boundary, mocked sandbox boundary.**
  - Postgres: localhost:5432 `grandline` database (same DB the dev backend
    uses; `make up && make migrate` is the prerequisite). Each test runs
    inside a fresh `AsyncSession` with explicit cleanup.
  - Redis: localhost:6379 db **index 1** (NOT 0 — db 0 is for dev). Mirror
    [test_den_den_mushi_integration.py:36-49](src/backend/tests/test_den_den_mushi_integration.py#L36-L49)
    fixture pattern: `pytest.skip` if Redis unavailable, `flushdb` after
    each test.
  - LLM: patch `DialSystemRouter.route` at the class level with a
    role-keyed canned-response helper. Each `CrewRole` returns the JSON
    the matching service prompt expects. **No real provider calls, no
    fallback chain, no rate limiter.**
  - Sandbox: register a stub `ExecutionBackend` that returns canned
    pytest results — no real Docker / GVisor execution. Reuse the
    existing `app.state.execution_service` slot via dependency-injection
    override.
- **Marker**: `pytestmark = pytest.mark.integration` — already configured
  in [pyproject.toml](src/backend/pyproject.toml). CI runs both `pytest`
  (default) and `pytest -m integration` (when infra is up); local devs
  run integration explicitly.
- **One test database, multiple isolated test runs.** Use a session-scoped
  `engine` fixture and a function-scoped `db_session` fixture that
  cleans tables between tests (DELETE FROM in reverse-FK order, or
  TRUNCATE … CASCADE if simpler).
- **Background-task lifecycle is observable** — the test calls
  `await PipelineService.start(...)` synchronously (no
  `asyncio.create_task` wrapping at the test layer; that's an API-layer
  concern). The graph runs to completion in the test's loop and the
  caller can assert on the resulting state directly.
- **Failure paths use the same canned-response helper, switched per
  test.** No new mock framework — just override one role's canned JSON
  to return a "test failures" or HelmsmanError trigger.
- **Concurrency assertion uses an in-flight counter probe**, not a
  patched `asyncio.Semaphore`. Wrap `ShipwrightService.build_code` in
  a thin probe that increments a shared counter on entry and decrements
  on exit, asserting the peak never exceeds `max_concurrency`. Mirrors
  the Phase 15.3 unit test pattern in
  [test_pipeline_graph.py](src/backend/tests/test_pipeline_graph.py)
  `test_semaphore_bounds_concurrency`.
- **Dep-ordering assertion uses event timestamps**, not internal hooks.
  The Redis stream records exact emit times for `pipeline_stage_completed`
  per-phase events; a phase whose `depends_on` includes phase X must
  have its `phase_built` event timestamp ≥ phase X's. Read from Redis
  via `mushi.replay(stream)` after the pipeline completes.
- **Resume-skips-satisfied uses pre-seeding**, not internal patches. The
  test inserts a `VoyagePlan`, `Poneglyph` per phase, and `HealthCheck`
  per phase directly via the test session, sets voyage status to
  `PAUSED`, then calls `PipelineService.start(...)`. Assert that the
  patched `DialSystemRouter.route` was called **0 times for Captain
  and Navigator and Doctor(write)**, and ≥ 1 time for Shipwright.

## Deliverables

### 1. Test infrastructure: `tests/integration/conftest.py` (new)

A new `tests/integration/` directory keeps the heavy fixtures away from the
fast-unit suite. Place a `__init__.py` (empty) there too.

**Fixtures** (function-scoped unless noted):

```python
@pytest.fixture(scope="session")
async def integration_engine() -> AsyncEngine: ...

@pytest.fixture
async def db_session(integration_engine: AsyncEngine) -> AsyncSession: ...
    """Yield a fresh AsyncSession; truncate all pipeline tables on teardown."""

@pytest.fixture
async def redis_client() -> Redis: ...
    """db=1; flushdb on teardown; pytest.skip if not reachable."""

@pytest.fixture
def mushi(redis_client: Redis) -> DenDenMushi: ...

@pytest.fixture
def stub_execution_service() -> ExecutionService: ...
    """ExecutionService backed by a StubExecutionBackend that returns
    pytest "all passed" results regardless of input."""

@pytest.fixture
def stub_git_service() -> GitService: ...
    """GitService backed by a no-op git backend; returns a fake SHA."""

@pytest.fixture
def stub_deployment_backend() -> InProcessDeploymentBackend:
    return InProcessDeploymentBackend()  # already in-process by design

@pytest.fixture
def role_keyed_router(mushi: DenDenMushi, voyage_id: uuid.UUID) -> DialSystemRouter: ...
    """Real DialSystemRouter wired with stub adapters that return canned
    JSON per role. The canned JSON is configurable per-test via a
    helper."""
```

**Cleanup** (`db_session` teardown):
```sql
TRUNCATE deployments, validation_runs, build_artifacts, shipwright_runs,
         health_checks, poneglyphs, voyage_plans, voyages,
         dial_configs, vivre_cards, crew_actions, users
RESTART IDENTITY CASCADE;
```
Run this both at fixture entry (clean slate from any prior leak) and exit
(don't pollute the next test).

**`StubExecutionBackend`** lives in `tests/integration/stubs.py`:
```python
class StubExecutionBackend(ExecutionBackend):
    """Returns canned pytest passed results. No real execution."""
    async def run(self, files: dict[str, str], command: list[str], ...) -> ExecutionResult:
        return ExecutionResult(
            exit_code=0,
            stdout="3 passed in 0.12s",
            stderr="",
            duration_seconds=0.1,
        )
```

**Canned-response helper** lives in `tests/integration/canned_llm.py`:
```python
def make_role_router(
    mushi: DenDenMushi,
    voyage_id: uuid.UUID,
    *,
    overrides: dict[CrewRole, str] | None = None,
) -> DialSystemRouter:
    """Build a DialSystemRouter with role-keyed stub adapters that return
    pre-canned JSON matching what each crew service's prompt expects."""
```

The default canned responses must produce a self-consistent voyage:
- **Captain**: a `VoyagePlanSpec` with 3 phases, phase 2 deps on 1, phase 3
  deps on [1, 2] — exercises both layers and dep ordering in one shape.
- **Navigator**: one `Poneglyph` per phase (3 total), with TDD requirements.
- **Doctor (write)**: one pytest `HealthCheck` per phase.
- **Shipwright**: a tiny passing python file per phase
  (e.g. `def add(a, b): return a + b`). Match
  [shipwright_service.py](src/backend/app/services/shipwright_service.py)'s
  expected JSON shape (`files`, `notes`).
- **Doctor (validate)**: `{"status": "passed", "diagnosis": null}`.
- **Helmsman**: deploy result with `status: "completed"` + a fake URL.

### 2. The integration test: `tests/integration/test_pipeline_integration.py` (new)

```python
pytestmark = pytest.mark.integration


class TestHappyPath:
    async def test_full_pipeline_runs_to_completed(
        self, db_session, mushi, role_keyed_router,
        stub_execution_service, stub_git_service, stub_deployment_backend,
    ) -> None:
        # Seed: user + voyage(CHARTED) + DialConfig(shipwright.max_concurrency=3)
        # Build PipelineService
        # await service.start(voyage, user_id, "build a calculator", "preview")
        # Assert: voyage.status == COMPLETED
        # Assert: VoyagePlan exists; 3 Poneglyphs; 3 HealthChecks;
        #         3 BuildArtifacts (all phase_status[i] == "BUILT");
        #         1 ValidationRun.status == "passed";
        #         1 Deployment.status == "completed"
        # Assert: Redis stream has expected event sequence
        # (pipeline_started, 6× stage_entered/stage_completed pairs,
        #  pipeline_completed; plus per-service events from the crew
        #  services — voyage_plan_created, poneglyph_drafted ×3,
        #  health_check_written ×3, code_generated ×3, tests_passed ×3,
        #  validation_passed, deployment_completed)
        # Assert: VivreCard count >= 12 (one per stage transition)

    async def test_event_ordering(...) -> None:
        # mushi.replay(stream) after completion
        # Assert: pipeline_started is first; pipeline_completed is last
        # Assert: all stage_entered comes before its matching stage_completed
        # Assert: helmsman events come after doctor validate events
```

```python
class TestParallelShipwright:
    async def test_max_concurrency_2_with_5_phases(...) -> None:
        # Override Captain canned response: 5 independent phases
        # DialConfig.role_mapping.shipwright.max_concurrency = 2
        # Wrap ShipwrightService.build_code with an in-flight counter probe
        # await service.start(...)
        # Assert peak in-flight ever observed <= 2
        # Assert all 5 phases ended up BUILT

    async def test_dep_ordering_respects_layers(...) -> None:
        # Captain returns 4 phases:
        #   phase 1 depends_on []
        #   phase 2 depends_on [1]
        #   phase 3 depends_on [1]
        #   phase 4 depends_on [2, 3]
        # Each Shipwright build sleeps a known amount via the probe.
        # await service.start(...)
        # Read 'tests_passed' events from Redis (per-phase).
        # Assert phase 4's timestamp >= max(phase 2, phase 3) timestamps.
        # Assert phase 2 and 3 timestamps >= phase 1 timestamp.
```

```python
class TestFailurePaths:
    async def test_doctor_validate_failure_marks_voyage_failed(...) -> None:
        # Override Doctor(validate) canned response → status="failed"
        # await service.start(...) raises PipelineError
        # Assert: voyage.status == FAILED
        # Assert: ValidationRun.status == "failed"
        # Assert: NO Deployment row (never reached deploying_node)
        # Assert: PipelineFailedEvent on Redis with stage="REVIEWING"

    async def test_helmsman_deploy_failure_marks_voyage_failed_with_diagnosis(...) -> None:
        # Override Helmsman canned response → trigger HelmsmanError
        # Assert: voyage.status == FAILED
        # Assert: Deployment row exists with status="failed" + diagnosis
        # Assert: PipelineFailedEvent on Redis with stage="DEPLOYING"
        # Assert: ValidationRun.status == "passed" (this stage succeeded)

    async def test_shipwright_phase_failure_cancels_layer(...) -> None:
        # 3 independent phases, Shipwright canned response for phase 2
        # raises ShipwrightError("BUILD_FAILED")
        # Assert: phase 1 BUILT, phase 2 FAILED, phase 3 in {PENDING, FAILED}
        # Assert: voyage.status == FAILED
```

```python
class TestResumeSkipsAlreadySatisfied:
    async def test_resume_from_paused_skips_planning_pdd_tdd(
        self, db_session, mushi, role_keyed_router_call_counter, ...
    ) -> None:
        # Pre-seed: voyage(PAUSED), VoyagePlan(3 phases), 3 Poneglyphs,
        #           3 HealthChecks; phase_status all PENDING
        # await service.start(...)
        # Assert call counter for CrewRole.CAPTAIN == 0
        # Assert call counter for CrewRole.NAVIGATOR == 0
        # Assert call counter for CrewRole.DOCTOR == 1 (validate, not write)
        # Assert call counter for CrewRole.SHIPWRIGHT == 3
        # Assert: voyage reached COMPLETED

    async def test_resume_partial_build_only_runs_missing_phases(...) -> None:
        # Pre-seed phase 1 BUILT (with BuildArtifact); phases 2,3 PENDING
        # await service.start(...)
        # Assert Shipwright.build_code called only for phases 2 and 3
        # Assert voyage COMPLETED
```

### 3. CI hook: optionally extend GitHub Actions

If the existing CI already runs `pytest -m integration`, no change. If it
doesn't, **do not add a new CI job in this PR** — gate that decision on
whether the user wants integration tests to run on every push (slow + needs
infra) or only on a label / manual trigger. Document the local-run command
in the test docstring:

```
# Local: requires Postgres + Redis up
make up && make migrate && \
  cd src/backend && pytest -m integration tests/integration/ -v
```

### 4. Decisions log entry

Append to [pdd/context/decisions.md](pdd/context/decisions.md):

> **Decision: Pipeline integration test uses real Postgres + Redis with
> mocked LLM and sandbox boundaries**
>
> **Date**: 2026-04-25 (or current date)
>
> **What was decided**: `tests/integration/test_pipeline_integration.py`
> exercises the full Voyage Pipeline against real Postgres (localhost:5432
> grandline DB) and real Redis (localhost:6379 db 1). Only two boundaries
> are mocked: (a) `DialSystemRouter.route` returns role-keyed canned
> JSON via stub `ProviderAdapter`s, (b) `ExecutionBackend` is a stub
> that returns "all tests passed". `InProcessDeploymentBackend` and
> `GitService` are real (the in-process deploy backend doesn't need
> infra by design; git operations run inside the same stub backend).
> Marked `@pytest.mark.integration` and skipped if infra unavailable.
> Concurrency assertions use an in-flight-counter probe; dep-ordering
> assertions read event timestamps from `mushi.replay(stream)`.
>
> **Why**: A unit-only test surface can't catch session-lifecycle bugs,
> transaction visibility issues across the background-task / request
> boundary, or Redis stream ordering edge cases. Mocking only the LLM
> + sandbox keeps the test fast (~5s) and deterministic while still
> exercising every other component for real. The role-keyed canned
> response helper centralizes the LLM mock so failure-path tests just
> override one role's response. Reusing `InProcessDeploymentBackend`
> + a stub `ExecutionBackend` avoids the Docker dependency for CI.
>
> **Don't suggest**: Mocking Postgres / Redis with fakes (defeats the
> purpose), running real LLM providers in CI (cost + flakiness),
> running the real GVisor backend in CI (Docker-in-Docker complexity),
> per-test database recreation (TRUNCATE + RESTART IDENTITY is faster).

## Test Plan

- [ ] `tests/integration/test_pipeline_integration.py` exists with the
  test classes outlined above
- [ ] `tests/integration/conftest.py` and `tests/integration/__init__.py`
  exist
- [ ] `tests/integration/stubs.py` and `tests/integration/canned_llm.py`
  exist
- [ ] `pytest -m integration tests/integration/ -v` passes when
  Postgres + Redis are up (local: `make up && make migrate`)
- [ ] All integration tests are individually runnable (no inter-test
  ordering dependency)
- [ ] `pytest tests/` (no marker) still passes 807+ existing tests; the
  new integration tests are skipped/excluded by default
- [ ] `ruff check app/ tests/` clean
- [ ] `mypy app/` clean (test files excluded from mypy as is project
  convention — verify against [mypy.ini / pyproject.toml] before
  declaring; if test files are included, ensure they pass too)
- [ ] `make smoke` (Phase 15.4 manual harness) still passes
- [ ] Decision logged in `pdd/context/decisions.md`

## Constraints

- **No new application code** — this phase is tests + test infrastructure
  only. If the integration test uncovers a real bug, fix it in a separate
  commit; the bug fix is scoped to the failing assertion (not a
  refactor).
- **Integration tests live under `tests/integration/`** — keep the unit
  suite fast. The pytest config already gates this with the
  `integration` marker.
- **Real Postgres on localhost:5432** — same DB the dev backend uses.
  Tests truncate pipeline tables on entry/exit; do NOT drop the schema.
- **Real Redis on localhost:6379 db=1** — never db=0 (collides with dev
  data). `flushdb` on teardown.
- **Mocked LLM at the `DialSystemRouter.route` boundary**, not at
  individual service methods. Each crew service stays real; the only
  injection point is the router. This catches bugs where a service
  passes the wrong shape to the router.
- **Mocked sandbox at `ExecutionBackend.run`** — same principle: don't
  mock at `ExecutionService` level. The backend boundary is the right
  seam.
- **Real `InProcessDeploymentBackend` + real `GitService`** — both are
  cheap and deterministic; mocking them adds noise without value. (The
  in-process deployment backend doesn't actually deploy; it just
  records a Deployment row.)
- **Skip cleanly if infra is missing** — `pytest.skip` with a clear
  message ("Postgres not available on localhost:5432" /
  "Redis not available on localhost:6379"). Never hang or fail
  obscurely on a missing service.
- **Each test is independent** — no shared state assumptions, no
  ordering dependencies, no fixture leak. Run any subset and they pass.
- **Concurrency probe must be deterministic** — use `asyncio.Lock` +
  in-flight counter + peak tracking. No `asyncio.sleep` magic numbers
  in assertions.
- **Dep-ordering test uses event timestamps**, not internal callbacks.
  Redis events are the public observability contract; assert against
  that.
- **Resume tests pre-seed via the test session** — same DB, same models,
  same shape the real services would write. No service mocks needed for
  the pre-seed path.
- **Failure-path tests must verify both the voyage state AND the event
  stream** — voyage.status, the matching `Validation`/`Deployment` row,
  AND a `PipelineFailedEvent` on the Redis stream with the right
  `stage`. All three or it's not a complete failure assertion.
- **No new CI job in this PR** — tests opt into integration via the
  marker; CI changes are a separate decision.
- **No commit or PR until the user signs off.**

## References

- Plan: [PLAN-voyage-pipeline.md](PLAN-voyage-pipeline.md) §Phase 5
- Phase 15.1 (PR #35): per-phase status gate, parallel-safe Shipwright
- Phase 15.2 (PR #36): pipeline guards
- Phase 15.3 (PR #37): master graph, PipelineService, pipeline events
- Phase 15.4 (PR #38): REST + SSE API + smoke harness
- Existing real-Redis fixture pattern:
  [tests/test_den_den_mushi_integration.py](src/backend/tests/test_den_den_mushi_integration.py)
- Pipeline service contract (don't modify):
  [services/pipeline_service.py](src/backend/app/services/pipeline_service.py)
- Pipeline graph + stage nodes:
  [crew/pipeline_graph.py](src/backend/app/crew/pipeline_graph.py)
- Pipeline events (5 types):
  [den_den_mushi/events.py](src/backend/app/den_den_mushi/events.py)
  (`PipelineStartedEvent` → `PipelineCompletedEvent` / `PipelineFailedEvent`)
- DialSystemRouter shape:
  [dial_system/router.py:57](src/backend/app/dial_system/router.py#L57) —
  `route(role, request) -> CompletionResult`
- Adapter contract:
  [dial_system/adapters/base.py](src/backend/app/dial_system/adapters/base.py)
- Crew services (5 of them, all need canned responses):
  - [captain_service.py](src/backend/app/services/captain_service.py) —
    expects VoyagePlanSpec JSON
  - [navigator_service.py](src/backend/app/services/navigator_service.py) —
    expects Poneglyph JSON
  - [doctor_service.py](src/backend/app/services/doctor_service.py) —
    expects HealthCheck list + ValidationResult JSON (two prompts)
  - [shipwright_service.py](src/backend/app/services/shipwright_service.py) —
    expects `{files: {path: content}, notes: ...}` JSON
  - [helmsman_service.py](src/backend/app/services/helmsman_service.py) —
    expects DeploymentBackend driver to handle the deploy
- Models that should have rows after a successful run:
  [voyage.py](src/backend/app/models/voyage.py) (`status=COMPLETED`,
  `phase_status={i: "BUILT"}`),
  [poneglyph.py](src/backend/app/models/poneglyph.py),
  [health_check.py](src/backend/app/models/health_check.py),
  [build_artifact.py](src/backend/app/models/build_artifact.py),
  [validation_run.py](src/backend/app/models/validation_run.py),
  [deployment.py](src/backend/app/models/deployment.py),
  [vivre_card.py](src/backend/app/models/vivre_card.py)
- Pytest config (markers + asyncio mode):
  [pyproject.toml](src/backend/pyproject.toml)
- Local infra setup (newly added in Phase 15.4):
  [Makefile](Makefile) — `make up && make migrate`
