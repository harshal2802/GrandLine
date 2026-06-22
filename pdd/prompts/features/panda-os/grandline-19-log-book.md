# Prompt: Log Book (cross-voyage memory)

**File**: pdd/prompts/features/panda-os/grandline-19-log-book.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: Phase 10 (Captain Agent + CaptainService.chart_course), Phase 16.0 (CrewAction helper / event publish patterns), the current Alembic head `d4e5f6a1b2c3` (voyage phase_status)
**Project type**: Backend (FastAPI + SQLAlchemy + Pydantic v2)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. A
competitive review of PandaOS surfaced its "local knowledge graph — never
re-explain your stack" pitch. GrandLine's Vivre Cards already checkpoint agent
state, but only **within** a single voyage; nothing carries learnings forward.
Every new voyage against the same repository re-discovers the same layout,
conventions, and gotchas from scratch.

In One Piece, a ship's **Log Book** is the durable record of everything learned
on past voyages — the knowledge the crew carries from one journey to the next.
Here, the Log Book is a **per-repo memory store that persists ACROSS voyages**.
The Captain recalls it at planning time so the crew doesn't re-learn a repo's
shape every time it charts a course against it.

The per-repo key is `Voyage.target_repo` (already a `String(500)` column). The
Log Book is keyed on that string so any voyage targeting the same repo shares one
body of prior knowledge. Writes are API-driven in this phase; an automatic
write-back from completed voyages is a noted follow-up (Phase 22 territory).

## Task

Implement the Log Book as a standard three-layer backend feature (model →
schema → service → API), plus a best-effort recall hook in the Captain:

1. **Model** (`app/models/log_book.py`) — `LogBookEntry`:
   - `id` UUID pk; `repo` `String(500)` indexed, NOT NULL (per-repo key, matches
     `Voyage.target_repo`); `voyage_id` UUID FK -> `voyages.id`, nullable (the
     voyage that produced the learning, if any); `author` `String(50)` NOT NULL
     (crew role string or `"user"`); `kind` `String(50)` NOT NULL (one of
     `convention`, `decision`, `layout`, `gotcha`, `summary`); `content` `Text`
     NOT NULL; `details` JSONB default dict, server_default `"{}"`;
     `created_at` timezone-aware, server_default `now()`.
   - Register in `app/models/__init__.py`.

2. **Migration** (`alembic/versions/<rev>_log_book.py`) — create
   `log_book_entries`; `down_revision='d4e5f6a1b2c3'`; index on `repo` and a
   composite index on `(repo, created_at)` for most-recent-first recall.

3. **Schemas** (`app/schemas/log_book.py`) — Pydantic v2:
   - `LogBookEntryCreate` (`repo`, `author`, `kind`, `content`, `details?`,
     `voyage_id?`), validating `kind` against the allowed set.
   - `LogBookEntryRead` (all fields + `id` + `created_at`; `from_attributes=True`).
   - `RecalledContext` (`repo`, `entries: list[LogBookEntryRead]`, `rendered: str`).

4. **Service** (`app/services/log_book_service.py`) — `LogBookService(session)`
   with `LogBookError(code, message)`:
   - `record(repo, author, kind, content, *, details=None, voyage_id=None)` —
     add + flush + commit + refresh (mirror `CaptainService` commit ordering).
   - `recall(repo, *, limit=20, kinds=None)` — most-recent-first, optional kind
     filter.
   - `render_context(repo, *, limit=20)` — format recalled entries into a
     prompt-injectable markdown block headed
     `## Log Book — prior knowledge for <repo>`; return `""` when empty so
     callers can no-op safely.
   - `reader(session)` classmethod consistent with `CaptainService.reader`.

5. **Captain integration** (`app/services/captain_service.py`):
   - Construct a `LogBookService` from the same session in `__init__` (NOT in
     `reader()`).
   - In `chart_course`, BEFORE invoking the graph: if `voyage.target_repo` is
     set, call `render_context(voyage.target_repo)` and, if non-empty, prepend it
     to the `task` passed into the graph (recalled block + `"\n\n---\n\n"` +
     original task). BEST-EFFORT: wrap in try/except, log a warning on failure,
     proceed with the original task. No behavior change when `target_repo` is
     None or the Log Book is empty.

6. **API** (`app/api/v1/log_book.py`) — kebab path, default-deny via
   `get_current_user`:
   - `GET /api/v1/log-book?repo=<str>&limit=<int>` -> `list[LogBookEntryRead]`.
   - `POST /api/v1/log-book` body `LogBookEntryCreate` -> `LogBookEntryRead` (201).
   - Register the router in `app/api/v1/router.py`.

## Input

- Existing `Voyage.target_repo` (`String(500)`, nullable) at
  `src/backend/app/models/voyage.py`.
- `CaptainService.chart_course` at `src/backend/app/services/captain_service.py`
  (commit/flush/refresh ordering, best-effort publish, `reader()` classmethod).
- `app/api/v1/dependencies.py` (`get_current_user`, `get_db`).
- Current Alembic head `d4e5f6a1b2c3`.
- Test patterns: `tests/test_captain_service.py`, `tests/test_captain_api.py`,
  `tests/test_models.py`, `tests/test_captain_schemas.py` (mocked AsyncSession,
  direct endpoint-function calls — no live DB).

## Output format

- Python files following existing conventions (async, fully type-annotated,
  Pydantic v2). One Piece terminology ("Log Book") in docstrings/comments/labels.
- New files only under `src/backend/app/` and `src/backend/tests/` (plus the PDD
  Poneglyph and `pdd/context/` doc updates).
- Unit tests mock `AsyncSession` with `unittest.mock`; API tests call the
  endpoint functions directly with mocked services (no Postgres).

## Constraints

- Strictly typed, async, Pydantic v2 — no `Any` abuse.
- No secrets in code.
- Captain recall is BEST-EFFORT and must never fail `chart_course`; existing
  Captain tests must keep passing.
- `kind` is a locked taxonomy: `convention`, `decision`, `layout`, `gotcha`,
  `summary`. Reject anything else at the schema boundary.
- `render_context` returns `""` (not `None`) when there is nothing to recall.
- Migration `down_revision` MUST be `'d4e5f6a1b2c3'`; index `repo` and
  `(repo, created_at)`.
- Default-deny: both endpoints require `get_current_user`.

## Edge Cases

- `recall` for a repo with no entries → empty list; `render_context` → `""`.
- `chart_course` with `target_repo=None` → unchanged task, no recall call effect.
- Log Book recall raises (DB hiccup) → logged warning, original task used, plan
  still produced.
- `kind` not in the allowed set → 422 at the API / `ValidationError` in schema.
- `limit` <= 0 → schema floors it (`ge=1`); `recall` honors the bound.
- `details` omitted → defaults to `{}` (model server_default + schema default).
- `voyage_id` omitted → entry is repo-scoped learning with no originating voyage.
- Very long `content` → stored as `Text`, no truncation (unlike CrewAction.summary).
