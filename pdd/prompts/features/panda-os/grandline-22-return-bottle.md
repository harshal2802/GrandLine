# Prompt: Return Bottle (close the loop)

**File**: pdd/prompts/features/panda-os/grandline-22-return-bottle.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: Phase 21 (Message in a Bottle — the `origin` JSONB column + its dict shape), Phase 19 (Log Book — `LogBookService.record`), the master pipeline completion hook in `pipeline_service.py`
**Project type**: Backend (FastAPI + SQLAlchemy + Pydantic v2 + httpx)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. A
competitive review of PandaOS surfaced the close of its flagship demo: after the
agents fix the bug, the workstation **drafts a reply to the human who reported
it** — closing the loop, not just shipping code. GrandLine's pipeline today ends
at "Helmsman deploys"; nobody tells the reporter.

In One Piece, when a castaway's **Message in a Bottle** (Phase 21) drifts in
carrying a plea for help, the crew that answers sends word back the same way — a
**Return Bottle** drifting home with news that the deed is done. Here, a Return
Bottle is the **completion-time outreach** that (a) posts a voyage summary back
to the originating GitHub issue using the Phase 21 `origin` metadata, and (b)
records a Log Book `summary` entry for the repo so future voyages recall what
this one accomplished.

This also closes a deferral: Phase 19 (Log Book) explicitly deferred
"auto write-back from completed voyages" to **"Phase 22 Return Bottle territory"**
so it wouldn't couple the Log Book to summary-generation quality. Phase 22
satisfies that deferral.

The outreach is **best-effort everywhere**: a failed Return Bottle must never
fail, roll back, or change the status of a voyage that already completed
successfully. Security is fixed-host: the outbound GitHub host is the configured
`github_api_base_url` (default `https://api.github.com`), **never** a host derived
from the untrusted `origin` payload; the bearer token is the existing
`github_api_token` setting, read from settings and never logged.

## Task

Implement Return Bottle as a service + a pipeline completion hook + a manual
re-send API, best-effort and fixed-host throughout:

1. **Setting** (`app/core/config.py`) — add `github_api_base_url: str =
   "https://api.github.com"` (env `GRANDLINE_GITHUB_API_BASE_URL`). REUSE the
   existing `github_api_token` for auth (do NOT add a new token). No new secrets.

2. **Service** (`app/services/return_bottle_service.py`) — `ReturnBottleService`
   constructed from `(session, settings)`, plus `ReturnBottleError(code, message)`:
   - `build_summary(voyage, *, deployment_url, duration_seconds, phase_count=None)
     -> str` — **PURE** (no I/O), unit-testable themed markdown summary: voyage
     title, status, phase count (when given), deploy URL (only when present),
     duration. Friendly/themed ("The crew has returned…").
   - `async post_to_github_issue(origin: dict, body: str) -> bool` — parse
     `origin["repo"]` as `owner/name`, POST
     `{base}/repos/{owner}/{name}/issues/{number}/comments` with headers
     `Authorization: Bearer <github_api_token>`, `Accept:
     application/vnd.github+json`, and JSON body `{"body": body}`, via
     `httpx.AsyncClient`. Return `True` on a 2xx, `False` otherwise. If the token
     is empty -> skip and return `False` (log info, no request). The outbound host
     is ALWAYS `{github_api_base_url}` — never taken from `origin`.
   - `async report(voyage, *, deployment_url=None, duration_seconds=None,
     phase_count=None, log_book=None) -> dict` — orchestrate best-effort outreach
     and return `{"issue_commented": bool, "log_book_recorded": bool}`:
     - If `voyage.origin` is a dict with `type == "github_issue"`: build the
       summary and call `post_to_github_issue` (swallow + log any exception ->
       `False`).
     - If `voyage.target_repo` is set: record a Log Book `summary` entry via the
       passed `LogBookService` (or one built from the session) so future voyages
       recall this voyage's outcome (swallow + log errors -> `False`). This
       satisfies the Phase 19 deferred write-back.
   - The httpx client is created INSIDE the method (`async with
     httpx.AsyncClient(...)`), not on the instance.

3. **Pipeline hook** (`app/services/pipeline_service.py`) — after the
   `PIPELINE_COMPLETED` CrewAction is recorded AND committed, call
   `ReturnBottleService(self._session, settings).report(voyage,
   deployment_url=..., duration_seconds=..., phase_count=...)` inside a try/except
   that logs a warning and NEVER raises. A failed Return Bottle must not fail or
   roll back the completed voyage. Re-fetch/refresh the voyage row if needed so
   `origin`/`target_repo` are loaded.

4. **API** (`app/api/v1/return_bottle.py`) — `POST
   /api/v1/voyages/{voyage_id}/return-bottle` (default-deny via
   `get_current_user`, owner-scoped): manually (re)send the Return Bottle for a
   COMPLETED voyage; returns the result dict. 404 if the voyage is missing/not
   owned; 409 `{"error":{"code":"VOYAGE_NOT_COMPLETED",...}}` if status !=
   COMPLETED. Register the router in `app/api/v1/router.py`.

## Input

- `Voyage` model at `src/backend/app/models/voyage.py` (`origin`, `target_repo`,
  `status`, `title`).
- The `origin` dict shape from Phase 21: `{"type":"github_issue","repo":
  "owner/name","issue_number":int,"issue_url":...,"issue_title":...,"sender":...,
  "received_at":...}`.
- `LogBookService.record(repo, author, kind, content, *, details, voyage_id)` at
  `src/backend/app/services/log_book_service.py` (`kind="summary"`).
- The pipeline completion block in `pipeline_service.py` (~lines 203-218):
  records `PIPELINE_COMPLETED` with `deployment_url`/`duration` in scope, commits.
- `Settings` at `src/backend/app/core/config.py` (`github_api_token`,
  `github_api_base_url`).
- Test patterns: `tests/test_trigger_service.py`, `tests/test_trigger_api.py`,
  `tests/test_standing_order_api.py`, `tests/test_pipeline_service.py`
  (mocked `AsyncSession`/services, `unittest.mock` for httpx — no Postgres, no
  network).

## Output format

- Python files following existing conventions (async, fully type-annotated,
  Pydantic v2). One Piece terminology ("Return Bottle") in docstrings/comments.
- New files only under `src/backend/app/` and `src/backend/tests/` (plus this PDD
  Poneglyph and `pdd/context/` doc updates).
- Unit tests mock `AsyncSession`/services with `unittest.mock`; httpx is mocked
  with `unittest.mock` (no `respx`, no live network). API tests call the endpoint
  functions directly with mocked services / patched settings.

## Constraints

- Strictly typed, async, Pydantic v2 where relevant — no `Any` abuse.
- **No secrets in code** — the token is the existing `github_api_token` (settings,
  env only) and is NEVER logged.
- **Fixed outbound host** — the GitHub host is `settings.github_api_base_url`,
  NEVER derived from `origin`. Only `api.github.com` (or the configured base) is
  contacted.
- **Best-effort everywhere on the completion path** — a Return Bottle failure
  (httpx error, DB error, malformed `origin`) is swallowed + logged and never
  fails or rolls back a completed voyage.
- Empty token -> skip the GitHub call (return `False`), don't error.
- No new Alembic migration (no new columns). If somehow needed, chain
  `down_revision='a7c9e1f3b5d2'`.

## Edge Cases

- Voyage with a `github_issue` origin + a `target_repo` -> both the issue comment
  and the Log Book write are attempted (`{"issue_commented": True,
  "log_book_recorded": True}` on success).
- Voyage with no `origin` (manually charted) -> no issue comment attempted
  (`issue_commented` is `False`); Log Book still written if `target_repo` set.
- Voyage with a non-`github_issue` origin -> no issue comment attempted.
- Voyage with no `target_repo` -> no Log Book write attempted.
- `github_api_token` empty -> issue comment skipped (`False`), logged at info.
- GitHub returns non-2xx -> `post_to_github_issue` returns `False`, voyage
  unaffected.
- httpx raises / DB raises mid-report -> swallowed, the corresponding result key
  is `False`, the voyage stays COMPLETED.
- Deploy URL present -> included in the summary; absent -> omitted cleanly.
- Manual API on a non-COMPLETED voyage -> 409 `VOYAGE_NOT_COMPLETED`; on a
  missing/not-owned voyage -> 404.
