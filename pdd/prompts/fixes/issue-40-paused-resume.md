# Fix: PAUSED voyages can't resume via POST /start (issue #40)

## Context

Phase 15 shipped a working pause primitive (`POST /voyages/{id}/pause` flips
`voyage.status` to `PAUSED`) but the matching resume path is broken. Every
stage node in [pipeline_graph.py](src/backend/app/crew/pipeline_graph.py)
opens with:

```python
if voyage.status == VoyageStatus.PAUSED.value:
    return {"paused": True}
```

So when a caller invokes `POST /voyages/{id}/start` on a PAUSED voyage, the
planning node sees `PAUSED` immediately and routes the graph to `pause_end`
without doing anything. The voyage stays paused forever and the API
contract becomes a lie. The Phase 15.5 integration test only exercises
"resume from CHARTED with pre-seeded artifacts" — the pure PAUSED→resumed
path has no coverage.

The user picked the **explicit `POST /resume`** approach over an implicit
status flip inside `/start`. Rationale: the explicit endpoint is more
discoverable in the OpenAPI surface, idempotent, and keeps `/start` and
`/resume` semantically distinct (start is "begin a fresh run", resume is
"continue where pause stopped"). The frontend's eventual UI affordance
also maps cleanly to a separate button.

**Locked decisions for this fix**:

- **New endpoint: `POST /voyages/{id}/resume`** — flips
  `voyage.status` from `PAUSED` to `CHARTED` and commits, then spawns the
  pipeline task the same way `/start` does. The graph picks up where it
  left off via the existing skip-already-satisfied logic (Phase 15.3).
- **`/start` semantics unchanged** — still rejects PAUSED with the same
  409 it does today (well, technically it currently routes to pause_end
  silently — change it to a clear 409 `VOYAGE_PAUSED_USE_RESUME` so
  callers get a deterministic error instead of a no-op success).
- **`/resume` is idempotent on non-PAUSED states** — CHARTED → 200 no-op
  (already runnable), running pipeline → 409 `PIPELINE_ALREADY_RUNNING`,
  COMPLETED/CANCELLED → 409 `VOYAGE_NOT_RESUMABLE`, FAILED → 200 (treat
  it like a re-attempt, same as how `require_can_enter_planning`
  accepts FAILED).
- **No graph changes** — the per-stage `if status == PAUSED` checks stay
  exactly as they are. The fix lives at the API layer; the graph never
  sees PAUSED because `/resume` flips the status first.
- **`StartVoyageRequest` body re-used for `/resume`** — same shape (task,
  deploy_tier, max_parallel_shipwrights). The `task` field is required
  by the schema even on resume; on resume the Captain stage is
  skip-already-satisfied (plan exists), so `task` is unused but must
  satisfy validation. Document this caveat in the endpoint's docstring.
- **Same background-task lifecycle as `/start`** —
  `app.state.pipeline_tasks` registry, `done_callback` cleanup,
  `task.cancel()` on `/cancel`. Don't duplicate the registry plumbing;
  factor a small helper if it becomes copy-paste.
- **Decision log**: append a follow-up entry to
  [pdd/context/decisions.md](pdd/context/decisions.md) — explain the
  explicit-endpoint choice and link to issue #40.

## Deliverables

### 1. New endpoint: `POST /voyages/{id}/resume`

In [app/api/v1/pipeline.py](src/backend/app/api/v1/pipeline.py):

```python
@router.post(
    "/resume",
    response_model=StartVoyageResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def resume_voyage(
    voyage_id: uuid.UUID,
    body: StartVoyageRequest,
    request: Request,
    user: User = Depends(get_current_user),
    voyage: Voyage = Depends(get_authorized_voyage),
    pipeline_service: PipelineService = Depends(get_pipeline_service),
) -> StartVoyageResponse:
    """Resume a PAUSED voyage. Flips status to CHARTED, then spawns the
    pipeline graph (which uses skip-already-satisfied to pick up from the
    next unsatisfied stage). Idempotent on FAILED (treats as re-attempt)
    and CHARTED (no-op flip). Rejects RUNNING (409) and terminal (409)."""
    # validation + flip + spawn task — see below
```

**Validation order** (raise the first applicable error):
1. If task is already running for this voyage → 409 `PIPELINE_ALREADY_RUNNING`.
2. If `voyage.status` is `COMPLETED` or `CANCELLED` → 409
   `VOYAGE_NOT_RESUMABLE` with a clear message.
3. If `voyage.status` is `PAUSED` or `FAILED` → flip to `CHARTED`, commit.
4. If `voyage.status` is already `CHARTED` → no flip, accept.
5. Anything else (`PLANNING`, `PDD`, `TDD`, `BUILDING`, `REVIEWING`,
   `DEPLOYING`) → 409 `VOYAGE_NOT_RESUMABLE` (a running pipeline owns
   those; cancel + restart is the workflow).

After the flip, the spawn block mirrors `/start` exactly. Factor the
shared body into a helper if it's longer than ~10 lines:

```python
def _spawn_pipeline_task(...) -> StartVoyageResponse:
    # registry + create_task + done_callback
```

**Error codes added to `_PIPELINE_ERROR_STATUS`**:
- `VOYAGE_NOT_RESUMABLE` → 409 Conflict

### 2. Improve `/start` rejection of PAUSED voyages

Currently `/start` lets a PAUSED voyage through and the graph silently
exits. Add a check before spawning:

```python
if voyage.status == VoyageStatus.PAUSED.value:
    raise _pipeline_http_exception(
        PipelineError(
            "VOYAGE_PAUSED_USE_RESUME",
            "Voyage is PAUSED; use POST /voyages/{id}/resume to continue",
        )
    )
```

Map `VOYAGE_PAUSED_USE_RESUME` to **409 Conflict** in
`_PIPELINE_ERROR_STATUS`.

### 3. Add `PipelineService.resume(voyage)`

Optional but cleaner than embedding the status flip in the API layer.
In [app/services/pipeline_service.py](src/backend/app/services/pipeline_service.py),
add:

```python
async def resume(self, voyage: Voyage) -> None:
    """Flip a PAUSED or FAILED voyage back to CHARTED. No-op on CHARTED.
    Raises PipelineError on terminal/active statuses."""
```

This keeps the API endpoint thin and gives integration tests a clean
seam to mock. If you'd rather inline it in the endpoint to keep the
service surface tight, that's also fine — just be consistent and
document the choice in the decision log.

### 4. Tests: `tests/test_pipeline_api.py`

Extend the existing test file with a new `TestResumeVoyage` class:

- `test_returns_202_and_spawns_task_when_voyage_paused` — verify status
  flipped to CHARTED before task spawn, registry entry present, body
  shape matches `StartVoyageResponse`.
- `test_returns_202_when_voyage_failed` (idempotent on FAILED).
- `test_returns_202_when_voyage_charted` (no-op flip, but accepts).
- `test_returns_409_when_voyage_completed`.
- `test_returns_409_when_voyage_cancelled`.
- `test_returns_409_when_pipeline_already_running`.
- `test_returns_409_when_voyage_running_planning_stage` (mid-stage
  transitional status — caller should cancel + restart).
- `test_validates_request_body` (extra field → 422, missing task → 422).
- `test_forbidden_for_other_users_voyage` (404 via
  `get_authorized_voyage`).

Update existing `TestStartVoyage`:
- Add `test_returns_409_when_voyage_paused_with_use_resume_code` —
  verify the new explicit rejection (was a silent no-op pre-fix).

### 5. Tests: `tests/integration/test_pipeline_integration.py`

Replace the comment-with-cross-reference workaround in
`TestResumeSkipsAlreadySatisfied` with real PAUSED → resumed coverage:

- Pre-seed the voyage with `status=PAUSED`, plan + 3 poneglyphs + 3
  health_checks, all phases PENDING.
- Call `service.resume(voyage)` (or hit the endpoint via the test
  harness — pick one and document why).
- Assert `service.start(voyage, ...)` then runs to COMPLETED with
  Captain/Navigator/Doctor(write) call counts == 0 and
  Shipwright/Doctor(validate)/Helmsman call counts >= 1.

If you embed status flip in the API endpoint (option 3 alternative),
the integration test should still cover the resume path end-to-end —
either by calling the endpoint or by replicating the flip + start in
the test body.

### 6. Decisions.md update

Append a new entry to [pdd/context/decisions.md](pdd/context/decisions.md):

> **Decision: PAUSED voyages resume via explicit `POST /resume` endpoint, not implicit `/start` status flip**
> **Date**: 2026-04-25
> **What was decided**: Added `POST /voyages/{id}/resume` that flips
> `voyage.status` from PAUSED (or FAILED) back to CHARTED and spawns
> the pipeline task. `POST /start` now rejects PAUSED with a clear 409
> `VOYAGE_PAUSED_USE_RESUME` error instead of silently no-oping. The
> graph's per-stage `if status == PAUSED` checks are unchanged; the
> fix lives entirely at the API layer because the graph never sees
> PAUSED on the resume path.
> **Why**: An explicit endpoint is more discoverable in the OpenAPI
> surface, semantically distinct from "begin a fresh run", and gives
> the frontend a clean affordance for the eventual resume button. The
> implicit-flip alternative would have made `/start` overloaded ("kick
> this voyage forward from wherever it is") which contradicts the
> existing 409 semantics for COMPLETED/CANCELLED. Idempotency on
> CHARTED/FAILED keeps `/resume` safe to retry.
> **Don't suggest**: implicit status flip in `/start`, adding a
> `force=true` body field, deriving the resume target stage from
> `phase_status` (skip-already-satisfied already does this), reading
> the previous status from a Voyage history table (no such table).

### 7. No graph or guard changes

- Do NOT modify `pipeline_graph.py` per-stage PAUSED checks.
- Do NOT modify `pipeline_guards.py`.
- Do NOT change `voyage.status` enum values.

## Test Plan

- [ ] `pytest tests/test_pipeline_api.py -v` — new `TestResumeVoyage`
  passes; updated `TestStartVoyage::test_returns_409_when_voyage_paused`
  passes.
- [ ] `pytest -m integration tests/integration/ -v` — updated
  `TestResumeSkipsAlreadySatisfied::test_resume_from_paused_skips_planning_pdd_tdd`
  uses `status=PAUSED` instead of CHARTED and covers the full resume
  flow.
- [ ] `pytest -q` — full suite green; no regressions on existing 826+ tests.
- [ ] `ruff check app/ tests/` clean.
- [ ] `mypy app/ --ignore-missing-imports` clean.
- [ ] `make smoke` (Phase 15.4 manual harness) still passes; optionally
  extend the smoke script to call `/resume` after `/pause` against a
  voyage with pre-seeded artifacts.
- [ ] Issue #40 acceptance criteria all met.
- [ ] Decision logged in `pdd/context/decisions.md`.

## Constraints

- **API-layer fix only** — do NOT touch `pipeline_graph.py`,
  `pipeline_guards.py`, or any crew service. The PAUSED-check semantics
  inside the graph are correct: they detect a pause that happened DURING
  a run, and that's still useful.
- **Status flip lives in `PipelineService.resume(voyage)`**, not in
  the endpoint body. Keep the endpoint thin so the integration test can
  call the service directly.
- **`/resume` accepts the same `StartVoyageRequest` body as `/start`** —
  don't introduce a new schema. Document that `task` is required by
  validation but unused on resume (Captain is skip-already-satisfied).
- **Idempotency table** — codify in the endpoint docstring:

  | voyage.status | Behavior | HTTP |
  |---|---|---|
  | PAUSED | flip → CHARTED, spawn task | 202 |
  | FAILED | flip → CHARTED, spawn task | 202 |
  | CHARTED | no flip, spawn task | 202 |
  | PLANNING/PDD/TDD/BUILDING/REVIEWING/DEPLOYING | reject | 409 `VOYAGE_NOT_RESUMABLE` |
  | COMPLETED | reject | 409 `VOYAGE_NOT_RESUMABLE` |
  | CANCELLED | reject | 409 `VOYAGE_NOT_RESUMABLE` |
  | (running task already in registry) | reject | 409 `PIPELINE_ALREADY_RUNNING` |
- **`POST /start` on PAUSED** must return 409 `VOYAGE_PAUSED_USE_RESUME`
  with a message that points to `/resume`. No silent success.
- **Background task plumbing must not be duplicated** — if
  `/start` and `/resume` end up with > 5 lines of identical
  registry/done_callback code, factor it into a private helper in
  `pipeline.py`.
- **Don't add unused-yet-anticipated features** — no `force=true`
  param, no resume-from-specific-stage knob, no resume history audit
  log. Just fix the bug.
- **No commit or PR until the user signs off.**

## References

- Issue: [#40](https://github.com/harshal2802/GrandLine/issues/40)
- Phase 15.3 (graph + service): [PR #37](https://github.com/harshal2802/GrandLine/pull/37)
- Phase 15.4 (REST + SSE): [PR #38](https://github.com/harshal2802/GrandLine/pull/38)
- Phase 15.5 (integration tests + parallel session fix):
  [PR #41](https://github.com/harshal2802/GrandLine/pull/41)
- Pipeline router (where the new endpoint lives):
  [app/api/v1/pipeline.py](src/backend/app/api/v1/pipeline.py)
- PipelineService (where `.resume()` lives):
  [app/services/pipeline_service.py](src/backend/app/services/pipeline_service.py)
- Per-stage PAUSED check (must NOT be removed):
  [app/crew/pipeline_graph.py:447](src/backend/app/crew/pipeline_graph.py#L447) and similar in every stage
- Skip-already-satisfied logic (what makes resume cheap):
  [app/crew/pipeline_graph.py — _make_planning_node etc.](src/backend/app/crew/pipeline_graph.py)
- VoyageStatus enum: [app/models/enums.py](src/backend/app/models/enums.py)
- Pipeline guards (note: `require_can_enter_planning` already accepts
  PAUSED — that's why pre-flight passes; the silent no-op is downstream):
  [app/services/pipeline_guards.py:42](src/backend/app/services/pipeline_guards.py#L42)
- API tests (where `TestResumeVoyage` lives):
  [tests/test_pipeline_api.py](src/backend/tests/test_pipeline_api.py)
- Integration tests (where the PAUSED→resumed path replaces the
  CHARTED workaround):
  [tests/integration/test_pipeline_integration.py](src/backend/tests/integration/test_pipeline_integration.py)
- Existing decision on pause/resume semantics (the `pdd/context/decisions.md`
  entry from Phase 15.3 covers DB-status-driven pause; this fix amends
  it with the resume API contract).
