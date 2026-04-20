# Phase 15.1: Shipwright Parallel-Safety Refactor

## Context

Phase 15 wires all five crew agents into a single master LangGraph. To unlock
**parallel Shipwright execution** (independent phases build concurrently for
clock-time wins), the landed Phase 13 Shipwright needs a correctness refactor
first. Two concurrent `build_code` calls on the same voyage currently race:

1. Both transition `voyage.status = BUILDING` then restore to `CHARTED`
2. Both run `delete-before-insert` on `BuildArtifact` scoped to `voyage_id`
   only — the second call can wipe the first's artifacts

This phase makes Shipwright **per-phase parallel-safe** without touching the
LangGraph graph (`app/crew/shipwright_graph.py`). The voyage-level status gate
is replaced by a per-phase gate backed by a new `Voyage.phase_status` JSONB
column. Concurrency is configurable per user via a new
`DialConfig.role_mapping.shipwright.max_concurrency` schema field (1–10,
default 1) — no DB migration needed because `role_mapping` is already JSONB.
The pipeline (Phase 15.3) will read this knob; Phase 15.1 only lands the
schema and the refactor.

This is a **refactor of landed code** (Phase 13 merged in PR #33). All
existing Shipwright tests must pass after the refactor — some will need their
assertions retargeted from `voyage.status` semantics to `phase_status`
semantics. Add new tests for the parallel-safety guarantees.

**Locked decisions driving this refactor** (see
`pdd/prompts/features/pipeline/PLAN-voyage-pipeline.md`):

- `Voyage.phase_status` is a JSONB column (not an enum table). Values are the
  string literals `"PENDING"`, `"BUILDING"`, `"BUILT"`, `"FAILED"`, stored
  directly. No SQLAlchemy `Enum` class — module-level constants in
  `shipwright_service.py` for readability.
- Voyage-level `voyage.status` transitions (`CHARTED → BUILDING → CHARTED`)
  are **removed** from `build_code`. Voyage.status stays `CHARTED` throughout.
  The future pipeline wraps the BUILDING stage with its own status transition.
- A phase in `BUILDING` or `BUILT` is not re-buildable → `ShipwrightError(
  "PHASE_NOT_BUILDABLE")` → 409. A phase in `PENDING` or `FAILED` is
  buildable (so retries and the pipeline's fresh runs both work).
- `BuildArtifact` delete-before-insert is scoped to
  `(voyage_id, phase_number)`.
- `max_concurrency` is validated at the Pydantic schema level (`ge=1, le=10`).
  If a DialConfig's stored JSONB contains an invalid value at read time, log
  a warning and fall back to 1 — never crash a voyage because of config
  drift.

### Existing infrastructure

| System | Module | Key interfaces |
|---|---|---|
| **Voyage model** | `app.models.voyage.Voyage` | Has `status`, `target_repo`. Add `phase_status: Mapped[dict[str, Any]]` |
| **Voyage status enum** | `app.models.enums.VoyageStatus` | Unchanged — still `CHARTED / PLANNING / ... / BUILDING / ...` |
| **Shipwright service** | `app.services.shipwright_service.ShipwrightService` | Refactor `build_code` gate + per-phase status transitions. Keep `reader()`, keep `SHIPWRIGHT_MAX_ITERATIONS = 3`, keep `_OUTPUT_TRUNCATE = 4000`, keep iteration loop + `_checkpoint_iteration`, keep `_maybe_commit_to_git`, keep success event publishing. |
| **Shipwright graph** | `app.crew.shipwright_graph` | **DO NOT TOUCH** — refactor is service-layer only |
| **Shipwright API** | `app.api.v1.shipwright.build_phase` | Update error mapping: `PHASE_NOT_BUILDABLE` → 409. The existing `VOYAGE_NOT_BUILDABLE` 409 check on `voyage.status != CHARTED` is **removed** (the voyage-level gate is gone — per-phase gate lives in the service). |
| **DialConfig schema** | `app.schemas.dial_config` | Add `max_concurrency` sub-schema under `role_mapping.shipwright`. Pydantic `Field(default=None, ge=1, le=10)`. |
| **BuildArtifact model** | `app.models.build_artifact.BuildArtifact` | Unchanged |
| **Events** | `app.den_den_mushi.events.BuildArtifactCreatedEvent` / `CodeGeneratedEvent` / `TestsPassedEvent` | Preserve payload shapes exactly — no changes |
| **Alembic head** | `c3d4e5f6a1b2_deployments.py` | New migration's `down_revision = "c3d4e5f6a1b2"` |

## Deliverables

### 1. Alembic migration — `Voyage.phase_status` JSONB column

One new migration under `src/backend/alembic/versions/`.
`down_revision = "c3d4e5f6a1b2"`. Suggested revision id:
`d4e5f6a1b2c3_voyage_phase_status`.

```python
op.add_column(
    "voyages",
    sa.Column(
        "phase_status",
        postgresql.JSONB(astext_type=sa.Text()),
        nullable=False,
        server_default=sa.text("'{}'::jsonb"),
    ),
)
# downgrade: op.drop_column("voyages", "phase_status")
```

Backfill is automatic — `server_default='{}'` populates existing rows.

### 2. Voyage model — add `phase_status`

In `app/models/voyage.py`:

```python
phase_status: Mapped[dict[str, Any]] = mapped_column(
    JSONB, nullable=False, default=dict, server_default=sa.text("'{}'::jsonb")
)
```

The dict is keyed by `str(phase_number)` (JSON keys are strings) → status
literal. Example:
`{"1": "BUILT", "2": "BUILDING", "3": "PENDING", "4": "FAILED"}`

Update `tests/test_models.py` `test_voyage_table_columns` to include
`"phase_status"` in the expected column set.

### 3. Shipwright service — per-phase gate

In `app/services/shipwright_service.py`, add module-level constants near the
top (after existing `SHIPWRIGHT_MAX_ITERATIONS` / `_OUTPUT_TRUNCATE`):

```python
PHASE_STATUS_PENDING = "PENDING"
PHASE_STATUS_BUILDING = "BUILDING"
PHASE_STATUS_BUILT = "BUILT"
PHASE_STATUS_FAILED = "FAILED"

_PHASE_BUILDABLE = frozenset({PHASE_STATUS_PENDING, PHASE_STATUS_FAILED})
```

Refactor `build_code` in the following order (preserving every other bit of
its current behavior — iteration loop, VivreCard checkpointing, event
publishing, git commit, BuildResultResponse return shape):

1. **Remove** the `voyage.status = VoyageStatus.BUILDING.value` / `.flush()`
   at the top (line ~97).
2. **Remove** the `except Exception: voyage.status = VoyageStatus.CHARTED.value`
   in the iteration-loop try (line ~149-152). Replace with a `try/except` that
   sets `voyage.phase_status[str(phase_number)] = PHASE_STATUS_FAILED`,
   flushes, and re-raises.
3. **Remove** the `voyage.status = VoyageStatus.CHARTED.value` before commit
   (line ~215). The voyage status is not touched at all.
4. **Add** a per-phase gate **before** the existing non-pytest check fails
   (so `VITEST_NOT_SUPPORTED` still beats `PHASE_NOT_BUILDABLE` ordering is a
   judgment call — see note below):
   ```python
   key = str(phase_number)
   current = voyage.phase_status.get(key, PHASE_STATUS_PENDING)
   if current not in _PHASE_BUILDABLE:
       raise ShipwrightError(
           "PHASE_NOT_BUILDABLE",
           f"Phase {phase_number} status is {current}; expected PENDING or FAILED",
       )
   ```
5. **Set** `voyage.phase_status[key] = PHASE_STATUS_BUILDING` + flush right
   before entering the iteration loop. **Important**: SQLAlchemy needs an
   explicit mutation signal for JSONB — assign a fresh dict or use
   `flag_modified(voyage, "phase_status")`. Recommended pattern:
   ```python
   new_status = dict(voyage.phase_status)
   new_status[key] = PHASE_STATUS_BUILDING
   voyage.phase_status = new_status
   await self._session.flush()
   ```
6. **On iteration-loop exception**: set `phase_status[key] = FAILED` (same
   fresh-dict pattern), flush, re-raise. No voyage.status touch.
7. **After iteration loop, before commit**: if `passed` is True, set
   `phase_status[key] = BUILT`. If `passed` is False (max iterations or parse
   error), set `phase_status[key] = FAILED`. The status-gate ordering now
   correctly reflects the terminal per-phase state.
8. **Scope the BuildArtifact delete-before-insert** to
   `(voyage_id, phase_number)` — this is **already** scoped to phase (lines
   ~183-188), so no change needed. Verify and move on.

**Order note**: the non-pytest `VITEST_NOT_SUPPORTED` check currently fires
first at line ~86. Keep that order — `VITEST_NOT_SUPPORTED` should beat
`PHASE_NOT_BUILDABLE` because a pytest-incompatible request is a deeper
problem than a temporarily-busy phase. Explicit test covers this (see Test
Plan).

**Error ordering in build_code**:
```
VITEST_NOT_SUPPORTED (existing, from non-pytest check)
  ↓
PHASE_NOT_BUILDABLE (new, from phase_status gate)
  ↓
... iteration loop runs ...
  ↓
BUILD_PARSE_FAILED (existing, from LLM parse-fail after max iterations)
```

### 4. Shipwright API — refactor the 409 gate

In `app/api/v1/shipwright.py` `build_phase`:

**Remove** the existing `voyage.status != CHARTED` 409 check (lines ~77-86).

Let the service raise `PHASE_NOT_BUILDABLE`; map that error code to 409 in
the existing `except ShipwrightError` block. Other existing error code → HTTP
mappings stay as-is. `VITEST_NOT_SUPPORTED` stays 422. `BUILD_PARSE_FAILED`
stays 422.

Keep the preflight 404 checks for missing Poneglyph and missing health checks
— those are API-layer concerns and do not change.

### 5. DialConfig schema — `max_concurrency` field

In `app/schemas/dial_config.py`, **add** a nested schema for the Shipwright
role's config:

```python
from pydantic import BaseModel, ConfigDict, Field

class ShipwrightRoleConfig(BaseModel):
    """Optional shape for role_mapping['shipwright'] sub-config. Other roles
    remain dict[str, Any] — this schema only defines what the pipeline reads.
    """
    model_config = ConfigDict(extra="allow")
    max_concurrency: int | None = Field(
        default=None,
        ge=1,
        le=10,
        description="Max parallel Shipwright phase builds (1-10, default 1).",
    )
```

**Do NOT change** the existing `DialConfigCreate` / `DialConfigUpdate` /
`DialConfigRead` schemas — `role_mapping` stays `dict[str, Any]` for
backwards compatibility with other roles. The `ShipwrightRoleConfig` schema
is a parser used by the pipeline (Phase 15.3 will import it). Phase 15.1
just lands the schema + its validation tests.

Add a runtime helper for safely reading the value at pipeline-time:

```python
def resolve_shipwright_max_concurrency(
    role_mapping: dict[str, Any] | None,
) -> int:
    """Read max_concurrency from role_mapping['shipwright']. Fall back to 1
    if absent, missing, or fails validation — log a warning in the fallback
    case so misconfiguration is visible."""
    if not role_mapping:
        return 1
    raw = role_mapping.get("shipwright")
    if not isinstance(raw, dict):
        return 1
    try:
        parsed = ShipwrightRoleConfig.model_validate(raw)
    except Exception:
        logger.warning(
            "Invalid shipwright role config in DialConfig; falling back to "
            "max_concurrency=1. raw=%r", raw,
        )
        return 1
    return parsed.max_concurrency or 1
```

Co-locate `resolve_shipwright_max_concurrency` in `app/schemas/dial_config.py`
or in a new `app/services/dial_config_resolver.py` (your call — keep it where
it will be easy for Phase 15.3 to import).

### 6. Decision log

Append one entry to `pdd/context/decisions.md` (place it after the most
recent entry):

```markdown
## Decision: Shipwright gates on per-phase status; concurrency is configurable
**Date**: 2026-04-19
**What was decided**: `ShipwrightService.build_code` gates on
`Voyage.phase_status[str(phase_number)]` (a JSONB map: PENDING / BUILDING /
BUILT / FAILED), not `voyage.status == CHARTED`. Voyage.status stays CHARTED
during per-phase builds; the future pipeline wraps the BUILDING stage with
its own voyage-level transition. `BuildArtifact` delete-before-insert is
scoped to `(voyage_id, phase_number)`. Concurrency is configurable via
`DialConfig.role_mapping.shipwright.max_concurrency` (1-10, default 1).
**Why**: Unlocks parallel Shipwright execution in Phase 15 Pipeline without
racing the voyage-level status or stomping per-phase artifacts. Users on
limited API plans (free-tier Anthropic, etc.) stay at max_concurrency=1;
users with Enterprise keys can set it higher. Token cost is unchanged;
only wall-clock improves.
**Don't suggest**: Reintroducing a voyage-level BUILDING status transition
inside build_code, deleting all BuildArtifacts on every per-phase build,
hardcoding max_concurrency, putting max_concurrency on the Voyage model
(it's a provider/plan concern, not a voyage concern).
```

## Test Plan

### `tests/test_shipwright_service.py` — update existing tests

The existing suite currently asserts voyage-level status transitions and the
`VOYAGE_NOT_BUILDABLE` 409 path via service. After this refactor:

- **Drop** assertions like `assert voyage.status == VoyageStatus.BUILDING.value`
  during in-flight builds and `assert voyage.status == VoyageStatus.CHARTED.value`
  after builds. Voyage.status stays CHARTED throughout build_code — a single
  sanity assertion `assert voyage.status == VoyageStatus.CHARTED.value` before
  and after is enough.
- **Drop** any test that sets `voyage.status = BUILDING` / `DEPLOYING` /
  `PAUSED` and asserts 409 at the service (the service no longer reads
  voyage.status).
- **Add** `test_build_code_transitions_phase_status_pending_to_built_on_success` —
  pre: `phase_status = {}`; post (success): `phase_status = {"1": "BUILT"}`.
- **Add** `test_build_code_transitions_phase_status_to_failed_on_max_iterations` —
  mock graph returns non-zero exit codes every iteration; post:
  `phase_status = {"1": "FAILED"}`.
- **Add** `test_build_code_transitions_phase_status_to_failed_on_exception` —
  mock graph raises on first iteration; assert `phase_status["1"] == "FAILED"`
  and the exception re-raises.

### `tests/test_shipwright_service.py` — NEW parallel-safety tests

- `test_rejects_phase_already_building` — pre-seed
  `voyage.phase_status = {"1": "BUILDING"}`, call `build_code(phase=1)`,
  assert `ShipwrightError.code == "PHASE_NOT_BUILDABLE"` and the message
  includes the current state.
- `test_rejects_phase_already_built` — same shape but with
  `{"1": "BUILT"}`. Also assert 409 when surfaced through the API (see
  API test below).
- `test_failed_phase_is_rebuildable` — pre-seed `{"1": "FAILED"}`, call
  `build_code(phase=1)`, assert it proceeds (use a mock graph that returns
  success) and `phase_status["1"] == "BUILT"` after.
- `test_pending_phase_is_buildable` — pre-seed `{}` (or `{"1": "PENDING"}`
  explicitly), assert `build_code` proceeds.
- `test_build_artifact_delete_scoped_to_phase` — pre-insert a `BuildArtifact`
  row for `(voyage, phase=2)`. Call `build_code(phase=1)` with a mock graph
  that generates one file. After: the original `phase=2` artifact is still
  present and a new `phase=1` artifact exists.
- `test_vitest_not_supported_beats_phase_not_buildable` — pre-seed
  `phase_status = {"1": "BUILDING"}` AND pass a vitest health_check. Assert
  `ShipwrightError.code == "VITEST_NOT_SUPPORTED"` (not `PHASE_NOT_BUILDABLE`)
  — locks the error ordering.
- `test_two_concurrent_build_code_calls_same_phase_one_wins` — use
  `asyncio.gather` to fire two `build_code(phase=1)` calls. After: exactly
  one succeeds (returns `BuildResultResponse`) and exactly one raises
  `ShipwrightError.code == "PHASE_NOT_BUILDABLE"`. Use the real test DB
  session to reflect actual race behavior; mock the graph to return a
  canned success. If a deterministic ordering requires `asyncio.sleep(0)`
  between `flush` and `gather`, add it.
- `test_two_concurrent_build_code_calls_different_phases_both_succeed` —
  fire `build_code(phase=1)` and `build_code(phase=2)` concurrently. Both
  succeed. `phase_status` ends as
  `{"1": "BUILT", "2": "BUILT"}`. Both phases produce distinct
  `BuildArtifact` rows.

### `tests/test_shipwright_api.py` — update existing tests

- **Drop** the test that seeds `voyage.status = BUILDING` (or similar
  non-CHARTED) and asserts 409 `VOYAGE_NOT_BUILDABLE`. That gate no longer
  exists at the API layer.
- **Add** `test_api_returns_409_phase_not_buildable_when_phase_in_progress` —
  pre-seed `phase_status = {"1": "BUILDING"}`, POST
  `/voyages/{id}/phases/1/build`. Assert 409 + body
  `{"error": {"code": "PHASE_NOT_BUILDABLE", "message": ...}}`.
- **Add** `test_api_returns_409_phase_not_buildable_when_phase_built` —
  pre-seed `phase_status = {"1": "BUILT"}`. Assert 409 same shape.
- Preserve existing 404 tests for missing Poneglyph / missing health_checks.
- Preserve existing 422 test for `VITEST_NOT_SUPPORTED`.

### `tests/test_models.py` — update voyage column set

Add `"phase_status"` to the expected columns in `test_voyage_table_columns`.

### `tests/test_dial_config_schemas.py` — NEW file

Add tests for `ShipwrightRoleConfig` validation:

- `test_accepts_none` — `ShipwrightRoleConfig(max_concurrency=None)` OK
- `test_accepts_minimum` — `max_concurrency=1` OK
- `test_accepts_maximum` — `max_concurrency=10` OK
- `test_accepts_defaults_to_none` — `ShipwrightRoleConfig()` → `max_concurrency is None`
- `test_rejects_zero` — `max_concurrency=0` → `ValidationError`
- `test_rejects_above_ceiling` — `max_concurrency=11` → `ValidationError`
- `test_rejects_negative` — `max_concurrency=-1` → `ValidationError`
- `test_rejects_string` — `max_concurrency="3"` → `ValidationError` (Pydantic
  strict int; set `strict=True` on the Field if needed — verify the default
  Pydantic v2 behavior coerces or rejects, prefer reject for clarity)

And tests for `resolve_shipwright_max_concurrency`:

- `test_returns_1_when_role_mapping_is_none`
- `test_returns_1_when_shipwright_key_missing`
- `test_returns_1_when_shipwright_is_not_a_dict` — e.g. `{"shipwright": "claude"}`
- `test_returns_value_when_valid` — `{"shipwright": {"max_concurrency": 5}}` → 5
- `test_returns_1_when_max_concurrency_invalid` — `{"shipwright": {"max_concurrency": 99}}` → 1 (logs warning)
- `test_returns_1_when_max_concurrency_absent` — `{"shipwright": {"provider": "anthropic"}}` → 1

Parameterize where practical.

## Constraints

- **Do NOT touch** `app/crew/shipwright_graph.py` — this refactor is service-layer only.
- **Do NOT change** `ShipwrightService.reader()` or any other service method signature besides `build_code`'s body. `build_code`'s signature stays `(voyage, phase_number, poneglyph, health_checks, user_id) -> BuildResultResponse`.
- **Do NOT rename** existing `ShipwrightError` codes (`VITEST_NOT_SUPPORTED`, `BUILD_PARSE_FAILED`). Only add `PHASE_NOT_BUILDABLE`.
- **Do NOT change** event payload shapes for `CodeGeneratedEvent`, `TestsPassedEvent`, `BuildArtifactCreatedEvent`. The pipeline (Phase 15.3) relies on current shapes.
- **Do NOT add** a new SQLAlchemy `Enum` type for phase_status. Use plain JSONB strings + module-level constants.
- **Do NOT add** `phase_status` reads or writes anywhere outside `ShipwrightService.build_code` in this phase — guards in Phase 15.2 will read it, and the pipeline in Phase 15.3 will read it. Other services stay unaware.
- **Do NOT change** the existing REST endpoint `POST /voyages/{id}/phases/{phase_number}/build` shape; only the error code for a busy/complete phase changes from `VOYAGE_NOT_BUILDABLE` to `PHASE_NOT_BUILDABLE` (both 409).
- **Do NOT weaken** any existing security check or rate limit.
- **Preserve** `SHIPWRIGHT_MAX_ITERATIONS = 3`. Preserve `_OUTPUT_TRUNCATE = 4000`.
- **Preserve** `_checkpoint_iteration` per-iteration VivreCards.
- **Preserve** `_maybe_commit_to_git` behavior.
- **Preserve** the `VivreCard(checkpoint_reason="build_complete")` after a successful build — its `state_data` shape is unchanged.
- **Log decision** to `pdd/context/decisions.md` as specified above.
- **All 633 existing tests must still pass** after the refactor (after updating the voyage-status-gate assertions listed above). ruff clean. mypy clean on `app/`.
- **Atomic commit ordering**: the existing atomic commit pattern (all DB writes in one `session.commit()`, then best-effort events) is preserved.
- **JSONB mutation**: use the fresh-dict-assign pattern (`new_status = dict(voyage.phase_status); new_status[key] = ...; voyage.phase_status = new_status`) to make SQLAlchemy track the change. Alternatively use `sqlalchemy.orm.attributes.flag_modified(voyage, "phase_status")`. Pick one and use it consistently.
- **Type hints**: `phase_status: Mapped[dict[str, Any]]`. Values are strings at runtime but typed as `Any` because JSONB can technically hold anything — the constants encode the intent.

## Out of Scope (do NOT do in this phase)

- Wiring `max_concurrency` into any concurrency-limiting code. Phase 15.3 does that via `asyncio.Semaphore`. Phase 15.1 only lands the schema + resolver helper.
- Changing the master LangGraph, pipeline guards, or any pipeline-level code — none exist yet.
- Changing voyage-level status transitions elsewhere (Captain, Navigator, Doctor, Helmsman services stay exactly as they are).
- Adding a `phase_status` read endpoint. The existing `GET /voyages/{id}` includes voyage fields automatically via the response model; confirm `phase_status` appears in the voyage read response schema or add it to `VoyageRead`/`VoyageResponse` if missing (small change, belongs here).
- Migrating DialConfig JSONB rows to the new `ShipwrightRoleConfig` shape. Existing rows without a shipwright key keep working; the resolver defaults to 1.
