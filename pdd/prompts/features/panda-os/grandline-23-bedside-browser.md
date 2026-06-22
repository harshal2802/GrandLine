# Prompt: Bedside Browser (browser-in-the-loop verification)

**File**: pdd/prompts/features/panda-os/grandline-23-bedside-browser.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: The Doctor (`DoctorService` + `doctor_graph`), the swappable-backend pattern (`ExecutionBackend`/`DeploymentBackend` + their factories and app-lifespan wiring), the CrewAction helper (`CrewActionType` enum + `record_action`/`publish_crew_action_recorded`)
**Project type**: Backend (FastAPI + SQLAlchemy + Pydantic v2)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. A
competitive review of PandaOS surfaced one more move worth adapting: after the
agents fix a bug, PandaOS **opens a real browser and checks the page actually
renders** — not just that the tests are green. GrandLine's Doctor only validated
via tests (`pytest -x`); nobody confirmed the page came up.

In One Piece the Doctor (Chopper) doesn't pronounce a patient healthy from the
chart alone — he goes to the **bedside** and checks. The **Bedside Browser** is
the Doctor's browser-in-the-loop verification: drive a headless browser against a
running app, assert the page renders, and surface a screenshot in the Ship's Log
— "tests pass AND the page renders".

Real browser execution must NEVER be required to import the app or run the test
suite. So, exactly like `ExecutionBackend` and `DeploymentBackend`, browser
execution sits behind a **swappable `BrowserCheckBackend` ABC selected by a
factory**. The v1 default is a deterministic `NullBrowserBackend` (no real
browser — the analogue of `InProcessDeploymentBackend`); a real
`PlaywrightBrowserBackend` is opt-in via config and **lazily imports** Playwright
inside `run` so app startup and CI never touch it.

## Task

Implement the Bedside Browser as schemas + a swappable backend + a thin
Doctor-mirroring service + a persisted model + a default-deny API, browser-free
by default:

1. **Schemas** (`app/schemas/browser_check.py`) — `BrowserAssertion`
   (`type: Literal["selector_present","text_present"]`, `value: str`),
   `BrowserCheckSpec` (`name`, `url`, `wait_for: str | None`, `assertions:
   list[BrowserAssertion]`, `capture_screenshot: bool = True`),
   `BrowserCheckResult` (`passed`, `screenshots: list[str]`, `console_errors`,
   `failed_assertions`, `duration_ms`), and `BrowserCheckRead`
   (`from_attributes=True` DB read model).

2. **Swappable backend** (`app/browser/`) — `BrowserCheckBackend` ABC (`async
   run(spec) -> BrowserCheckResult`; `async close()`) + `BrowserBackendError`;
   `NullBrowserBackend` (deterministic v1 default — assertion passes unless its
   `value` is empty; placeholder screenshot ref `"null-backend://<name>.png"`
   when `capture_screenshot`); `PlaywrightBrowserBackend` (lazily imports
   Playwright inside `run`; raises `BrowserBackendError` if absent); and
   `create_browser_backend(settings)` selecting on `browser_backend: str =
   "null"` (env `GRANDLINE_BROWSER_BACKEND`), unknown -> `ValueError`.

3. **Model + migration** (`app/models/browser_check.py`,
   `alembic/versions/b8d4f2a6c1e3_browser_checks.py`) — `BrowserCheck` (`id`,
   `voyage_id` FK indexed, `phase_number` nullable, `url`, `passed`,
   `screenshot_ref` nullable, `console_errors`/`failed_assertions` JSONB default
   list, `created_at`). Register in `models/__init__.py`. Migration
   `down_revision='a7c9e1f3b5d2'`.

4. **CrewActionType** (`app/services/crew_action_helper.py`) — add
   `BROWSER_CHECK_RUN = "browser_check_run"`.

5. **Service** (`app/services/bedside_browser_service.py`) —
   `BedsideBrowserService(session, mushi=None)` + `BedsideBrowserError(code,
   message)`. `run_browser_check(voyage, phase_number, spec, backend) ->
   BrowserCheck` runs the spec via the injected backend, persists a
   `BrowserCheck`, records a `BROWSER_CHECK_RUN` CrewAction (`CrewRole.DOCTOR`)
   whose `details` carry `screenshot_ref` + `passed` so the Ship's Log surfaces
   the screenshot, commits atomically, refreshes, and publishes the crew-action
   event best-effort (mirroring Doctor commit/refresh/publish ordering).
   `list_browser_checks(voyage_id)` reads newest-first.

6. **API** (`app/api/v1/bedside_browser.py`, default-deny, owner-scoped) — `POST
   /api/v1/voyages/{voyage_id}/phases/{phase_number}/browser-check` (body
   `BrowserCheckSpec`) -> 201 `BrowserCheckRead`, pulling the backend from
   `request.app.state.browser_backend`; `GET
   /api/v1/voyages/{voyage_id}/browser-checks` -> list `BrowserCheckRead`.
   Register the router in `router.py`.

7. **App wiring** (`app/main.py`) — `app.state.browser_backend =
   create_browser_backend(settings)` in lifespan startup; `await
   app.state.browser_backend.close()` on shutdown (next to the
   execution/deployment backends).

## Input

- The swap pattern to mirror: `app/execution/backend.py` + `factory.py` +
  `gvisor_backend.py`; `app/deployment/backend.py` + `in_process.py` (the real v1
  default; the Null backend is its analogue).
- `app/main.py` lifespan (~lines 49-90) — how `execution_service` /
  `deployment_backend` are constructed + closed.
- `app/services/doctor_service.py` — commit/refresh/publish ordering, Error
  class, CrewAction usage to mirror.
- `app/services/crew_action_helper.py` — `CrewActionType` enum (add a member),
  `record_action`/`publish_crew_action_recorded`.
- Test patterns: `tests/test_deployment_backend.py`,
  `tests/test_execution_backend.py`, `tests/test_doctor_service.py`,
  `tests/test_return_bottle_api.py` (mocked `AsyncSession`/backends; `unittest.mock`;
  no Postgres, no browser).

## Output format

- Python files following existing conventions (async, fully type-annotated,
  Pydantic v2). One Piece terminology ("Bedside Browser") in docstrings/comments.
- New backend artifacts under `src/backend/app/`, tests under `src/backend/tests/`
  (plus this Poneglyph + `pdd/context/` doc updates).
- Unit tests mock `AsyncSession`/backends with `unittest.mock` and inject a
  `NullBrowserBackend` or a stub; the Playwright backend's missing-library path is
  tested by patching the import (no Playwright install, no real browser).

## Constraints

- Strictly typed, async, Pydantic v2 — no `Any` abuse.
- **Playwright import is LAZY** (inside `run`, never at module top level) so app
  startup and the whole test suite never require it; an absent Playwright raises
  a clear `BrowserBackendError`, never an opaque `ImportError`.
- **Playwright is NOT added to `requirements.txt`** — it is an optional, opt-in
  backend. To use it: `pip install playwright && python -m playwright install
  chromium`, then set `GRANDLINE_BROWSER_BACKEND=playwright`.
- The default stays `NullBrowserBackend` — deterministic and CI-safe.
- No secrets in code.
- Default-deny: the API requires `get_current_user` and is owner-scoped via
  `get_authorized_voyage` (404 on missing/foreign voyage).
- New Alembic revision chains to the current head (`down_revision='a7c9e1f3b5d2'`);
  single head.

## Edge Cases

- Assertion with an empty `value` -> Null backend treats it as a failing,
  malformed assertion (`passed=False`, recorded in `failed_assertions`).
- `capture_screenshot=False` -> no screenshot ref; `screenshot_ref` on the row is
  NULL and the CrewAction `details.screenshot_ref` is `None`.
- `phase_number` may be `None` (a voyage-level, not phase-specific, check).
- Crew-action event publish fails (Redis down) -> swallowed + logged; the run is
  durable (the DB row + CrewAction already committed).
- `browser_backend` set to an unknown value -> `create_browser_backend` raises
  `ValueError` at startup (fail fast, not silently defaulting).
- Playwright selected but not installed -> `run` raises `BrowserBackendError` with
  install guidance; import of the module/app is unaffected.
- Missing/not-owned voyage -> 404 via `get_authorized_voyage`.
