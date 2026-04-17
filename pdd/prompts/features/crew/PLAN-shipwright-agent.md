# Implementation Plan: Shipwright Agent (Phase 13)

**Created**: 2026-04-17
**Issue**: #14
**Complexity**: High — iteration loop in the graph, parallel invocations, novel DB model for per-phase build runs, git commit path
**Estimated prompts**: 1 (single PDD prompt, matching Captain/Navigator/Doctor precedent)

## Summary

The Shipwright is a **phase-scoped developer agent**. A single invocation takes
one `phase_number` for a voyage, reads that phase's Poneglyph and the matching
`HealthCheck` rows (the failing tests from the Doctor), and enters an iteration
loop: **generate code → run phase tests in the sandbox → on failure, feed the
test output back into the prompt → regenerate → re-run**, up to
`max_iterations`. On success, it commits the generated source files to the
Shipwright's git branch and emits `CodeGeneratedEvent` + `TestsPassedEvent`.

One invocation = one phase. Callers (Phase 15's voyage pipeline, or a user hitting
the API directly) can fan out — multiple Shipwright invocations run concurrently
against independent phases, each in its own sandbox session with its own LLM
conversation state.

Same three-layer crew pattern as Captain/Navigator/Doctor (`graph → service → API`
with a `reader()` factory), atomic DB commit that includes a `VivreCard`
checkpoint per iteration, best-effort event publishing after commit, best-effort
git commit path.

## Phases

### Phase 1 (single prompt): Shipwright Agent end-to-end

**Produces**:
- `alembic/versions/<rev>_build_artifacts.py` — migration adding the
  `build_artifacts` and `shipwright_runs` tables
- `app/models/build_artifact.py` — `BuildArtifact` SQLAlchemy model
  (one row per source file produced per phase)
- `app/models/shipwright_run.py` — `ShipwrightRun` model (one row per
  `build_code` invocation; stores iteration count, final status, pytest output)
- `app/schemas/shipwright.py` — Pydantic schemas:
  `BuildArtifactSpec`, `ShipwrightOutputSpec`, `BuildCodeRequest`,
  `BuildResultResponse`, `BuildArtifactRead`, `BuildArtifactListResponse`
- `app/schemas/build_artifact.py` — `BuildArtifactRead` (mirrors
  `schemas/health_check.py`)
- `app/crew/shipwright_graph.py` — LangGraph graph with nodes:
  `generate → run_tests → [conditional: done | refine]` in a loop
- `app/services/shipwright_service.py` — `ShipwrightService` with
  `build_code(voyage, phase_number, user_id)` and
  `get_build_artifacts(voyage_id, phase_number=None)`
- `app/api/v1/shipwright.py` — `POST /voyages/{id}/phases/{phase_number}/build`,
  `GET /voyages/{id}/phases/{phase_number}/build`,
  `GET /voyages/{id}/build-artifacts`
- `app/den_den_mushi/events.py` — add `CodeGeneratedEvent` and
  `TestsPassedEvent` (if not already defined); wire into `AnyEvent`
- `app/api/v1/router.py` — include the new router
- Tests: `tests/test_shipwright_schemas.py`, `tests/test_shipwright_graph.py`,
  `tests/test_shipwright_service.py`, `tests/test_shipwright_api.py`,
  `tests/test_models.py` (extended)

**Depends on**:
- Navigator (`Poneglyph` rows must exist) — PR #28, merged
- Doctor (`HealthCheck` rows must exist) — PR #32, merged
- `ExecutionService` — used for sandboxed pytest runs during the loop
- `GitService` — used for the best-effort final commit on success

**Risk**: High — the iteration loop introduces state that Captain/Navigator/
Doctor didn't need. Test-output feedback into the prompt is novel. Parallelism
implies per-invocation isolation, not shared caches. Git commit on success has
the same best-effort semantics as Doctor.

**Prompt**: `pdd/prompts/features/crew/grandline-13-shipwrights.md`

## Key design decisions (locked before prompt)

1. **One invocation = one phase.** The API is `POST /voyages/{id}/phases/{phase_number}/build`,
   not a voyage-level build endpoint. This is the parallelism primitive — the
   future voyage pipeline (Phase 15) fans out one invocation per phase and
   awaits them concurrently. Shipwright itself has no internal parallelism.

2. **Iteration loop lives in the graph.** LangGraph `StateGraph` nodes:
   - `generate` — LLM call via `CrewRole.SHIPWRIGHT` with system prompt +
     user message built from Poneglyph + health-check sources + (if iteration > 1)
     last run's pytest output.
   - `run_tests` — calls `ExecutionService.run(user_id, ExecutionRequest(
     command="python -m pytest -x --tb=short",
     files=generated_files | test_files, timeout_seconds=120))`.
   - **Conditional edge**: if `exit_code == 0` → `END`. Else if
     `iteration < max_iterations` → back to `generate` with an incremented
     iteration counter and the failure output added to state. Else → `END`
     with `error="MAX_ITERATIONS_EXCEEDED"`.
   - `max_iterations = 3` (constant `SHIPWRIGHT_MAX_ITERATIONS`).

3. **Two new models**:
   - `ShipwrightRun`: one row per `build_code` call. Holds `voyage_id`,
     `phase_number`, `poneglyph_id`, `status` (`passed` | `failed` |
     `max_iterations`), `iteration_count`, `exit_code`, `passed_count`,
     `failed_count`, `total_count`, `output` (last 4000 chars of pytest stdout),
     `created_at`.
   - `BuildArtifact`: one row per generated source file, linked to the
     ShipwrightRun via `shipwright_run_id`. Holds `voyage_id`, `phase_number`,
     `file_path`, `content`, `language` (`python` | `typescript`),
     `created_by="shipwright"`, `created_at`.

   Rationale: `ShipwrightRun` is the equivalent of Doctor's `ValidationRun` —
   one row per invocation for observability. `BuildArtifact` mirrors
   `HealthCheck` — one row per file with the content verbatim. Git branch
   is the externalized source of truth; the DB rows are the structured,
   queryable record for the Observation Deck.

4. **Replace-mode per phase.** Re-invoking on the same phase deletes existing
   `BuildArtifact` rows for that `(voyage_id, phase_number)` before inserting.
   `ShipwrightRun` rows are append-only (history preserved). Same lesson as
   Navigator/Doctor — re-drafts replace, history of the attempt is retained.

5. **Path safety (Doctor lesson).** `BuildArtifactSpec.file_path` uses the
   same `_validate_relative_path` validator pattern Doctor added in PR #32 —
   reject absolute paths, drive/scheme prefixes, and `..` traversal. LLM
   output is untrusted and feeds both the sandbox and the host-side git commit.

6. **Graph state shape** (TypedDict):
   ```python
   class ShipwrightState(TypedDict):
       voyage_id: uuid.UUID
       phase_number: int
       poneglyph: dict[str, Any]          # parsed PoneglyphContentSpec
       health_checks: list[dict[str, str]] # [{file_path, content, framework}]
       iteration: int                      # 1-indexed
       max_iterations: int
       generated_files: dict[str, str]     # file_path -> content
       last_test_output: str | None        # stdout+stderr from prev run
       exit_code: int | None
       passed_count: int
       failed_count: int
       total_count: int
       status: Literal["passed", "failed", "max_iterations"] | None
       error: str | None                   # parse failures, not test failures
   ```

7. **Structured `DoctorError`-style exception**: `ShipwrightError(code, message)`
   with codes:
   - `BUILD_PARSE_FAILED` — LLM returned malformed JSON after retries inside
     the loop (not test failures — those are normal).
   - `BUILD_MAX_ITERATIONS` — iteration loop exhausted without green tests.
   - `PHASE_NOT_FOUND` — no Poneglyph for the requested phase_number.
   - `HEALTH_CHECKS_NOT_FOUND` — no HealthCheck rows for the phase.
   - API layer maps parse/iter errors to 422 and the not-found pair to 404.

8. **Status lifecycle**: voyage moves to transient `BUILDING` during
   `build_code`; restores to `CHARTED` on both success and failure so
   re-invocation is possible. (Add `VoyageStatus.BUILDING` if missing from
   enum — **check first**; project.md says phases 1-10 defined it but verify.)

9. **`ShipwrightService.reader(session)`** — classmethod returning a
   session-only instance for the GET endpoints, same pattern as Captain/
   Navigator/Doctor.

10. **Best-effort git commit** (after DB commit, on success only):
    - `git_service.create_branch(voyage.id, user_id, "shipwright", base_branch="main")`
    - `git_service.commit(voyage.id, user_id,
      f"feat(phase-{phase_number}): Shipwright implementation",
      crew_member="shipwright", files=generated_files)`
    - `git_service.push(voyage.id, user_id, branch)`
    - Wrapped in a single try/except — logs a warning on failure, never
      fails the request. Skip if `voyage.target_repo` is not set.

11. **Events** (best-effort publish after DB commit):
    - `CodeGeneratedEvent(voyage_id, phase_number, shipwright_run_id,
      file_count)` — always published on success.
    - `TestsPassedEvent(voyage_id, phase_number, shipwright_run_id,
      passed_count)` — published alongside `CodeGenerated` when tests green.
    - No event on `BUILD_MAX_ITERATIONS` — that's an error response; the
      voyage status reset is the observable signal. (Optionally add
      `TestsFailedEvent` later; not required by the issue.)

12. **Single Dial System call per iteration** — one LLM call, one JSON
    response `{"files": [{"file_path": "...", "content": "...",
    "language": "python"}]}`. Same `strip_fences` + `json.loads` +
    `ShipwrightOutputSpec.model_validate()` flow as Navigator/Doctor. On
    parse failure inside the loop: try ONE more LLM call with the parse
    error appended; if that also fails, raise `ShipwrightError(
    "BUILD_PARSE_FAILED")`.

13. **VivreCard checkpoint per iteration** — during the loop, after each
    `run_tests` node completes, the service persists a lightweight VivreCard
    (`crew_member="shipwright"`, `state_data={"iteration": N,
    "exit_code": X, "file_count": Y}`,
    `checkpoint_reason="iteration"`). This is the "no work lost" guarantee —
    if a provider failover happens mid-loop, the next invocation can see how
    far the previous one got. Implementation: the service owns the loop
    orchestration wrapper around graph invocations so it can checkpoint
    between iterations (graph itself is pure; service is the orchestrator).

    **Subtlety**: LangGraph's `.ainvoke()` runs the whole graph to completion.
    To checkpoint per iteration, the service either (a) runs the graph with
    `recursion_limit=1` in a Python loop, calling DB commit between runs,
    or (b) uses LangGraph's built-in checkpointer. For v1, option (a) —
    the service's loop wraps single-iteration graph invocations and owns
    the VivreCard writes. Keeps DB persistence out of the graph (graph
    stays side-effect-free except for the LLM/sandbox calls its nodes make).

14. **API responses** (`BuildResultResponse`):
    ```python
    class BuildResultResponse(BaseModel):
        voyage_id: uuid.UUID
        phase_number: int
        shipwright_run_id: uuid.UUID
        status: Literal["passed", "failed", "max_iterations"]
        iteration_count: int
        passed_count: int
        failed_count: int
        total_count: int
        file_count: int
        summary: str
    ```
    201 on first-time success, 200 on re-invocation replace. 409 if voyage
    status is not `CHARTED`. 404 for missing poneglyph/health-checks
    (API-layer pre-check via `NavigatorService.reader` and
    `DoctorService.reader`, following Doctor's 404-not-422 pattern).

15. **Shipwright system prompt** is explicit that it is implementing code
    to satisfy *pre-written failing tests*. The LLM receives the health
    check test file(s) verbatim as part of the user message, plus the
    Poneglyph's `task_description`, `test_criteria`, and `file_paths`.
    On iteration 2+, it additionally receives the previous pytest
    `stdout[-2000:]` with a "the tests still fail. fix the issues
    reported below" directive.

## Risks & Unknowns

- **Parallel invocation contention on `voyage.status`**: two Shipwrights
  racing to set `status = BUILDING` on the same voyage both think they
  own it. For v1, sequential enforcement at the API layer (one in-flight
  per voyage) is simplest. Better long-term: move phase-level status off
  the voyage row into a new `phase_status` map (future work). **Locking
  decision**: v1 keeps the voyage-level status check (409 if already
  `BUILDING`). The Phase 15 voyage pipeline will sequence Shipwright
  invocations per-phase; user-level parallelism across phases waits for
  the phase_status refactor. **This is a scope-cut, log in decisions.md.**

- **Max iterations = 3 arbitrariness**: chosen to match typical Claude/
  GPT-4 code-writing attention span. Configurable via an env var in a
  follow-up; not exposed via API yet. If 3 proves too low in Phase 15
  integration tests, bump the constant — no schema change needed.

- **pytest not installed in sandbox**: same risk Doctor had. Mitigation
  is the same — mock `ExecutionService` in unit tests; leave the real
  end-to-end check to Phase 15's pipeline integration test.

- **Token budget**: feeding test output back into the prompt inflates
  tokens each iteration. Cap `last_test_output` at 2000 chars and
  truncate verbosely. Consider dropping the original test criteria from
  iteration 2+ since they're now implicit in the test content — skip for
  v1 to keep the prompt construction simple.

- **Non-Python languages**: Shipwright must also produce TypeScript for
  frontend phases. For v1 the test runner is `pytest` only; if a phase's
  `health_checks[0].framework == "vitest"`, the service returns early
  with `ShipwrightError("VITEST_NOT_SUPPORTED")`. Document explicitly
  in the prompt. Vitest support is a follow-up phase.

## Decisions Needed

All locked above — proceeding to prompt generation. Three decisions worth
logging to `pdd/context/decisions.md` after implementation:
1. Shipwright invocation is **phase-scoped** (not voyage-scoped).
2. Iteration loop is **service-owned**, not graph-owned, to enable
   per-iteration VivreCard checkpointing without graph side effects.
3. `BuildArtifact` + `ShipwrightRun` split mirrors the Doctor's
   `HealthCheck` + `ValidationRun` split — per-file rows linked to
   per-run rows.

## Next step

Run `/pdd-skill:pdd-prompts` with this plan in hand, producing
`pdd/prompts/features/crew/grandline-13-shipwrights.md`.
