# Implementation Plan: Doctor Agent (Phase 12)

**Created**: 2026-04-16
**Issue**: #13
**Complexity**: High — two distinct operating modes, new DB model, git write path
**Estimated prompts**: 1 (single PDD prompt, matching Captain/Navigator precedent)

## Summary

The Doctor is a two-mode QA agent:

1. **Pre-build (TDD)**: reads a voyage's Poneglyphs, asks the Dial System to generate failing tests per phase, persists them as `HealthCheck` rows, and publishes `HealthCheckWrittenEvent`. Tests are optionally committed to a Doctor git branch via the existing `GitService`.
2. **Post-build (Validate)**: takes a set of Shipwright-produced files, materializes them alongside the stored health-check tests in a sandbox, runs pytest, persists the result, and publishes either `ValidationPassedEvent` or a new `ValidationFailedEvent`.

Both modes go through the existing crew agent three-layer pattern (`graph → service → API`) with `reader()` factory, atomic commits (HealthCheck + VivreCard), and best-effort event publishing. Follows Navigator/Captain precedent exactly.

## Phases

### Phase 1 (single prompt): Doctor Agent end-to-end

**Produces**:
- `alembic/versions/<rev>_health_checks.py` — migration adding the `health_checks` table
- `app/models/health_check.py` — SQLAlchemy model (`HealthCheck`)
- `app/schemas/doctor.py` — Pydantic schemas
- `app/schemas/health_check.py` — `HealthCheckRead` (separate file, mirrors `schemas/poneglyph.py`)
- `app/crew/doctor_graph.py` — LangGraph two-node graph for test generation
- `app/services/doctor_service.py` — `DoctorService` with `write_health_checks` and `validate_code`
- `app/api/v1/doctor.py` — `POST /voyages/{id}/health-checks`, `GET /voyages/{id}/health-checks`, `POST /voyages/{id}/validation`
- `app/den_den_mushi/events.py` — add `ValidationFailedEvent` (symmetric with `ValidationPassedEvent`)
- `app/api/v1/router.py` — wire the new router
- Tests: `tests/test_doctor_schemas.py`, `tests/test_doctor_graph.py`, `tests/test_doctor_service.py`, `tests/test_doctor_api.py`

**Depends on**: Navigator (Poneglyphs must exist), GitService (for the optional commit path), ExecutionService (for pytest execution). All three are already in place after PR #31 merge.

**Risk**: Medium — running pytest inside a sandbox is the novel piece; everything else is a direct analogue of Captain/Navigator.

**Prompt**: `pdd/prompts/features/crew/grandline-12-doctor.md`

## Key design decisions (locked before prompt)

1. **New HealthCheck model** — mirror the `Poneglyph` shape:
   ```
   id (UUID PK)
   voyage_id (UUID FK, indexed)
   poneglyph_id (UUID FK nullable, indexed)  # links back to the Poneglyph that produced it
   phase_number (int)
   file_path (String(500))                    # relative path inside the target repo, e.g. "tests/test_auth.py"
   content (Text)                             # the test source code
   framework (String(20))                     # "pytest" | "vitest"
   last_run_status (String(20) nullable)      # "passed" | "failed" | null (never run)
   last_run_output (Text nullable)            # raw captured stdout/stderr from the last run
   last_run_at (DateTime nullable)
   metadata_ (JSONB nullable)
   created_by (String(50), default="doctor")
   created_at (DateTime)
   ```
   Why: separating `HealthCheck` from `Poneglyph` keeps Doctor's lifecycle fields (`last_run_status`, `last_run_output`) independent and lets us query validation state per file without JSONB gymnastics.

2. **Two service methods, one graph** — the graph is the pre-build test-generation graph only. The post-build `validate_code` method does *not* run a graph; it shells out to pytest via `ExecutionService` and parses the exit code. Generating tests is an LLM task; running them is not.

3. **Transient statuses reuse existing enum values** — `VoyageStatus.TDD` during `write_health_checks`, `VoyageStatus.REVIEWING` during `validate_code`. Both restore to `CHARTED` on success *and* failure (replannable lifecycle). No new enum values needed.

4. **LLM prompt produces one JSON batch** — same pattern as Navigator: one Dial System call per voyage, returns `{"health_checks": [{"phase_number": N, "file_path": "...", "content": "..."}]}`. Single call keeps cost predictable and is consistent with the established pattern. Framework selection (`pytest` vs `vitest`) is inferred from the Poneglyph's `file_paths` (`.py` → pytest, `.ts`/`.tsx` → vitest, default pytest).

5. **Re-draft replaces (Fix #1 lesson from Navigator)** — `write_health_checks` deletes existing `HealthCheck` rows for the voyage before inserting new ones, so re-invocation replaces instead of duplicating.

6. **Phase alignment check (Fix #5 lesson)** — validate that every LLM-returned `phase_number` exists in the current Poneglyph set; if not, raise `DoctorError("HEALTH_CHECK_PHASE_MISMATCH", ...)`.

7. **Git commit is opt-in and best-effort** — Doctor is an LLM agent in this phase; the git branch commit is only attempted when a `GitService` + `user_id` are supplied and the voyage has a `target_repo`. When `target_repo` is absent, skip the commit path entirely and log it. This matches how the issue is scoped: "Tests written to Doctor's git branch" — the row in the DB is the source of truth; the git commit is the externalization, and the integration test for it is mocked.

8. **Validation input contract** — `validate_code(voyage, shipwright_files: dict[str, str])` takes a dict of `{file_path: content}`. The DoctorService layers the shipwright files + the stored `HealthCheck` files into the sandbox (via `ExecutionService.run`), invokes `python -m pytest -x --tb=short --json-report --json-report-file=/tmp/doctor.json`, and parses the JSON report. Pass/fail is decided by pytest's exit code; the raw output is stored on each `HealthCheck.last_run_output` for observability.

9. **`ValidationFailedEvent`** — add it to `events.py` + `AnyEvent` union. Symmetric with `ValidationPassedEvent`. Payload includes `failed_count`, `total_count`, and a truncated error summary.

10. **Doctor system prompt tells the LLM to write *failing* tests** — explicit requirement in the system prompt: "The implementation does not exist yet. Your tests should reference functions, classes, and files that will only exist after the Shipwrights implement them. Tests must fail when run now; this is by design (TDD)."

## Risks & Unknowns

- **Running real pytest inside the sandbox**: `ExecutionService` already exists and works; the piece we haven't exercised is `files=` injection + a python binary with pytest installed. The sandbox image may not have pytest installed out of the box. **Mitigation**: mock `ExecutionService` in tests; include a TODO note that a real end-to-end voyage run is Phase 15's responsibility.
- **vitest vs pytest framework inference**: if a Poneglyph has mixed `.py` and `.ts` files, we pick the dominant one. Rare enough in practice that a deterministic rule is fine.
- **Concurrent write/validate**: if a user triggers `validate_code` while `write_health_checks` is still running, both will try to flush status transitions. **Mitigation**: the 409 check at the API layer (status must be `CHARTED`) prevents this, same pattern as Navigator.

## Decisions Needed

All resolved above — proceeding to prompt generation.

## Next step

Run `/pdd-skill:pdd-prompts` with this plan in hand, producing `pdd/prompts/features/crew/grandline-12-doctor.md`.
