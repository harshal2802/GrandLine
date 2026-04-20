# Phase 15.2: Transition Guards + PipelineError

## Context

Phase 15 wires all five crew agents into a single master LangGraph
(`CHARTED → PLANNING → PDD → TDD → BUILDING → REVIEWING → DEPLOYING →
COMPLETED`). Each stage transition has pre-conditions — the pipeline should
refuse to enter a stage whose dependencies aren't satisfied (e.g. can't
enter BUILDING unless every planned phase has a health_check).

This phase centralizes those pre-conditions into **six pure predicate
helpers** in a new module `app/services/pipeline_guards.py`. Each helper
raises a single `PipelineError(code, message)` on violation. The helpers
are declarative, DB-object-only (no DB access, no I/O, no LLM calls), and
testable in isolation.

These guards also drive **skip-already-satisfied-stages on resume**: when a
voyage resumes from `PAUSED` or `FAILED`, the pipeline calls the guards to
decide whether to re-run a stage or skip to the next. If Poneglyphs already
cover every phase, there's no need to re-invoke the Navigator — the guard
will pass and the pipeline moves on. That's a real token-cost savings on
re-run after a fix.

No graph logic, no service composition, no API endpoint work in this
phase. Phase 15.3 will call these guards from `PipelineService`.

**Locked decisions driving this phase** (see
[PLAN-voyage-pipeline.md](PLAN-voyage-pipeline.md)):

- Guards are **pure predicates** over DB-loaded objects. They receive the
  Voyage and the relevant artifacts (plan, poneglyphs, health_checks,
  build_artifacts, validation_run) — they do NOT query the DB themselves.
  The caller (pipeline service) is responsible for loading.
- Guards raise `PipelineError(code, message)` on violation. One exception
  class for all pipeline-transition errors, distinguished by `.code`.
- Every guard returns `None` on success (matches the existing
  `HelmsmanError` / `DoctorError` / `ShipwrightError` "raise on failure"
  convention across the codebase).
- The **"can enter reviewing"** guard checks two things: every planned
  phase has at least one `BuildArtifact` row, AND the voyage's
  `phase_status[str(phase_number)] == "BUILT"` for every planned phase.
  The `phase_status` check was introduced in Phase 15.1 — this guard is
  its first consumer.
- `Voyage.status` legal starting points for `require_can_enter_planning`:
  `CHARTED`, `PAUSED`, `FAILED`. Re-running from `COMPLETED` or
  `CANCELLED` requires explicit cancel/reset (out of scope for v1).

## Deliverables

### 1. New module: `app/services/pipeline_guards.py`

**Exports**:

- `PipelineError(Exception)` with `.code: str` and `.message: str`
  attributes (mirroring `ShipwrightError` at
  [src/backend/app/services/shipwright_service.py:41-47](src/backend/app/services/shipwright_service.py#L41-L47)
  and `HelmsmanError` — same `__init__(self, code, message)` shape).
- Six guard functions, each raising `PipelineError` on violation:
  - `require_can_enter_planning(voyage: Voyage) -> None`
  - `require_can_enter_pdd(voyage: Voyage, plan: VoyagePlan | None) -> None`
  - `require_can_enter_tdd(voyage: Voyage, plan: VoyagePlan, poneglyphs: list[Poneglyph]) -> None`
  - `require_can_enter_building(voyage: Voyage, plan: VoyagePlan, health_checks: list[HealthCheck]) -> None`
  - `require_can_enter_reviewing(voyage: Voyage, plan: VoyagePlan, build_artifacts: list[BuildArtifact]) -> None`
  - `require_can_enter_deploying(voyage: Voyage, latest_validation: ValidationRun | None) -> None`

**Error code taxonomy** — lock each guard to exactly one code, so tests
and callers can pattern-match without relying on message text:

| Guard | Failure condition | Code |
|---|---|---|
| `require_can_enter_planning` | `voyage.status not in {CHARTED, PAUSED, FAILED}` | `VOYAGE_NOT_PLANNABLE` |
| `require_can_enter_pdd` | `plan is None` | `PLAN_MISSING` |
| `require_can_enter_tdd` | any planned phase has zero poneglyphs | `PONEGLYPHS_INCOMPLETE` |
| `require_can_enter_building` | any planned phase has zero health_checks | `HEALTH_CHECKS_INCOMPLETE` |
| `require_can_enter_reviewing` | any planned phase has zero artifacts OR `phase_status[str(phase)] != "BUILT"` for any planned phase | `BUILD_INCOMPLETE` |
| `require_can_enter_deploying` | `latest_validation is None` OR `latest_validation.status != "passed"` | `VALIDATION_NOT_PASSED` |

**Plan parsing**: guards that receive `plan: VoyagePlan` should pull the
list of planned phase numbers from `plan.phases` (JSONB column).
Parse via `VoyagePlanSpec.model_validate(plan.phases)` at
[src/backend/app/schemas/captain.py:23](src/backend/app/schemas/captain.py#L23)
and iterate `.phases`. Do NOT re-validate the dependency graph here —
`VoyagePlanSpec.validate_plan_graph` already guarantees phase_number
uniqueness + acyclic deps at write time. Guards just read the planned
`phase_number`s.

**Implementation notes**:

- Use `from __future__ import annotations` at the top (matches the rest
  of `app/services/`).
- Import `VoyageStatus` from `app.models.enums` — don't hardcode the
  string `"CHARTED"` etc.
- Import `PHASE_STATUS_BUILT` from `app.services.shipwright_service`
  (landed in Phase 15.1).
- `Poneglyph` / `HealthCheck` / `BuildArtifact` / `ValidationRun` /
  `Voyage` / `VoyagePlan` are all in `app.models.*`.
- Error messages should name the specific missing phase(s) when
  relevant: `f"Phases {sorted(missing)} missing health_checks"` — the
  test suite will assert the phase numbers appear in the message for
  the "incomplete" guards.
- Keep each function under ~15 lines. These are predicates, not
  workflows.
- Module docstring: one-paragraph summary of the role of this file in
  the pipeline (gatekeepers, pure predicates, no I/O).

### 2. New tests: `tests/test_pipeline_guards.py`

One test class per guard function. Cover:

**`TestRequireCanEnterPlanning`**:
- `test_allows_charted`
- `test_allows_paused`
- `test_allows_failed`
- `test_rejects_completed` → `VOYAGE_NOT_PLANNABLE`
- `test_rejects_planning` → `VOYAGE_NOT_PLANNABLE`
- `test_rejects_cancelled` → `VOYAGE_NOT_PLANNABLE`

**`TestRequireCanEnterPdd`**:
- `test_allows_when_plan_exists`
- `test_rejects_when_plan_is_none` → `PLAN_MISSING`

**`TestRequireCanEnterTdd`**:
- `test_allows_when_every_phase_has_poneglyph`
- `test_rejects_when_any_phase_missing_poneglyph` → `PONEGLYPHS_INCOMPLETE`
- `test_rejects_when_no_poneglyphs_at_all` → `PONEGLYPHS_INCOMPLETE`
- `test_message_lists_missing_phase_numbers` — build a 3-phase plan,
  give poneglyph for phase 1 only, assert the raised message contains
  `"2"` and `"3"` somewhere
- `test_ignores_extra_poneglyphs_for_phases_not_in_plan` — plan has
  phases 1, 2; provide poneglyphs for 1, 2, 99 — should pass

**`TestRequireCanEnterBuilding`**:
- `test_allows_when_every_phase_has_health_check`
- `test_rejects_when_any_phase_missing_health_check` → `HEALTH_CHECKS_INCOMPLETE`
- `test_rejects_when_no_health_checks` → `HEALTH_CHECKS_INCOMPLETE`
- `test_message_lists_missing_phase_numbers`
- `test_multiple_health_checks_per_phase_counts_as_covered` — a single
  phase may have many `HealthCheck` rows; guard just needs ≥1 per phase

**`TestRequireCanEnterReviewing`**:
- `test_allows_when_all_phases_built_with_artifacts`
- `test_rejects_when_artifact_missing_for_phase` → `BUILD_INCOMPLETE`
- `test_rejects_when_phase_status_not_built` → `BUILD_INCOMPLETE`
  (artifacts present but `phase_status[phase] == "BUILDING"` or
  `"FAILED"`)
- `test_rejects_when_phase_status_missing_for_phase` → `BUILD_INCOMPLETE`
  (artifacts present but `phase_status` dict missing the key entirely)
- `test_message_lists_missing_phase_numbers`

**`TestRequireCanEnterDeploying`**:
- `test_allows_when_latest_validation_passed`
- `test_rejects_when_latest_validation_is_none` → `VALIDATION_NOT_PASSED`
- `test_rejects_when_latest_validation_failed` → `VALIDATION_NOT_PASSED`
- `test_rejects_when_latest_validation_has_unknown_status` → `VALIDATION_NOT_PASSED`

**`TestPipelineError`**:
- `test_init_sets_code_and_message`
- `test_is_exception` — `isinstance(PipelineError("X", "msg"), Exception)`
- `test_str_shows_message`

**Test fixtures**:
- Use `MagicMock` for `Voyage`, `VoyagePlan`, `Poneglyph`, `HealthCheck`,
  `BuildArtifact`, `ValidationRun` — same pattern as
  [test_shipwright_service.py](src/backend/tests/test_shipwright_service.py).
  No DB needed; these are pure predicates.
- For `VoyagePlan`, set `plan.phases` to a real dict matching
  `VoyagePlanSpec` shape: `{"phases": [{"phase_number": 1, "name":
  "x", "description": "y", "assigned_to": "shipwright",
  "depends_on": []}, ...]}`. The guard will validate-parse it.
- For `Voyage.phase_status`, use real dicts (not MagicMock) so guards
  can do real `.get(key)` lookups. Same lesson as Phase 15.1.

### 3. No other files touched

- Do NOT touch `app/services/shipwright_service.py`,
  `app/crew/*`, `app/api/*`, or any migrations. Guards are a new module
  with no consumers yet — Phase 15.3 will wire them in.
- Do NOT export `PipelineError` from a broader package init (leave it
  importable as `from app.services.pipeline_guards import PipelineError`).

## Test Plan

- [ ] All new tests in `tests/test_pipeline_guards.py` pass
- [ ] All 665 existing tests still pass (no regressions — this phase
  adds a module, doesn't modify existing code)
- [ ] `ruff check app/ tests/` clean
- [ ] `mypy app/` clean (pre-existing `jose` stub warning is ignorable)
- [ ] Each guard function has ≥1 passing test and ≥1 failing-path test
- [ ] Error-code taxonomy from the table above is 1:1 with test
  assertions — no guard ever raises a code outside its row
- [ ] "Incomplete" guards (TDD, BUILDING, REVIEWING) have a test
  asserting the raised message mentions the missing phase numbers
- [ ] Log one decision to `pdd/context/decisions.md` (see Constraints)

## Constraints

- **Pure predicates only** — no DB queries, no LLM calls, no event
  publishing, no state mutation. Guards receive fully-loaded objects.
  The caller (Phase 15.3 pipeline service) owns the loading.
- **One error class, code-distinguished** — use `PipelineError(code,
  message)`, not a separate exception per guard. Mirrors the
  `ShipwrightError` / `HelmsmanError` convention.
- **No new dependencies** — everything needed already exists in
  `app.models.*` and `app.schemas.captain`.
- **No changes to existing code paths** — this is a pure-addition phase.
  Do not refactor the five crew services, the existing error classes,
  or the `Voyage` model. Phase 15.3 will wire these guards in.
- **Match existing style**: `from __future__ import annotations`,
  `logger = logging.getLogger(__name__)` if logging is needed (it
  likely isn't — guards raise, they don't log), type hints on every
  parameter and return, single-line docstring per function.
- **Do NOT add a shared `app/services/errors.py` catch-all module** —
  existing pattern is one error class per service file (ShipwrightError
  in shipwright_service.py, HelmsmanError in helmsman_service.py).
  Follow it: `PipelineError` lives in `pipeline_guards.py`.
- **Log one decision** to
  [pdd/context/decisions.md](pdd/context/decisions.md) as part of this
  phase. Suggested text: *"Pipeline transition pre-conditions are
  enforced by six pure-predicate guards in
  `app/services/pipeline_guards.py`, each raising
  `PipelineError(code, message)`. Guards receive DB-loaded objects
  and do no I/O — the pipeline service is responsible for loading.
  This also enables skip-already-satisfied-stages on resume: the
  pipeline calls the next guard; if it passes, the stage is skipped
  with no service / LLM call."*
- **No commit or PR until the user signs off** — land the prompt,
  then run TDD implementation, then review before committing.

## References

- Plan: [pdd/prompts/features/pipeline/PLAN-voyage-pipeline.md](PLAN-voyage-pipeline.md)
- Phase 15.1 landed: [PR #35](https://github.com/harshal2802/GrandLine/pull/35) — provides
  `PHASE_STATUS_BUILT` constant and `Voyage.phase_status` column
- Existing error convention:
  [src/backend/app/services/shipwright_service.py:41-47](src/backend/app/services/shipwright_service.py#L41-L47),
  `HelmsmanService` equivalent in `helmsman_service.py`
- Plan-phase parsing: [src/backend/app/schemas/captain.py](src/backend/app/schemas/captain.py) — `VoyagePlanSpec`
