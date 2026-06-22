# Prompt: Real preview backend — run the built app in the Cabin (Phase B0)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-B0-preview-backend.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: Phase 0b (**the Cabin** — `CabinBackend`/`CabinService`, `NullCabinBackend`
default, `GVisorCabinBackend` opt-in with a LAZY `aiodocker` import), Phase 0a (the Sea
Chest, materialized into the Cabin), Auth (Phase 4 — `get_current_user`,
`get_authorized_voyage`, default-deny middleware), `Settings` (`GRANDLINE_` env prefix),
and the established swappable-backend pattern. `aiodocker` MUST stay a LAZY import (never
module-top) so app startup and the test suite never need Docker.

**Project type**: Backend (FastAPI + Pydantic v2 + SQLAlchemy async)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. The
**Live App** workstream (PLAN-deck-capabilities.md, Workstream B = B0 → B1 → B2 → B3)
lets a user actually run the app the crew just built. Today the deployment layer
(`InProcessDeploymentBackend`) is a **STUB**: it records a synthetic URL
(`http://preview.voyage-xxxx.local`) and runs **nothing**.

**B0** makes "preview" real: it launches the crew's app as a **long-running process
inside the user's Cabin** (Phase 0b), captures a **real reachable URL + logs**, and
**reaps it on a hard lifetime cap**. B0 is the linchpin of Workstream B. Scope is
**start / status / logs(tail) / stop** — log STREAMING is B1, the embedded iframe is B2,
and the interactive PTY terminal is B3 (separate later phases).

PLAN reference: PLAN-deck-capabilities.md, Workstream B, Phase B0 ("Real preview
backend … launch the crew's app as a long-running subprocess inside the user's Cabin …
capture a real reachable URL, tee stdout/stderr to a log sink. Extend the Cabin contract
with `start_service / logs / stop`. Replaces the synthetic-URL stub. Network: localhost +
allow-listed only; hard lifetime cap.").

## Locked design decisions

- **Preview = a long-running process inside the per-user Cabin** (NOT the deploy stub).
  We extend the Cabin contract with long-running service support rather than touching the
  pipeline's `InProcessDeploymentBackend` — a standalone `PreviewService` over
  `CabinService` keeps the deploy pipeline byte-identical.
- **Swappable backend, Null default.** The Cabin already mirrors the
  `ExecutionBackend`/`DeploymentBackend`/`BrowserCheckBackend` seam. The Null backend
  gives a deterministic, container-free, CI-safe preview (fake-but-stable
  `http://127.0.0.1:<port>` URL, canned logs, `starting→running→stopped` transitions);
  `GVisorCabinBackend` is the opt-in real implementation (lazy `aiodocker`).
- **Hard max lifetime + reaping.** A preview is stamped with a started-at and a hard max
  lifetime (`preview_max_lifetime_seconds`, default 1800s). `reap_expired` stops previews
  past their cap so no long-running, network-capable, credential-bearing process orphans.
- **Process-local registry, v1 single-worker.** The `PreviewService` per-user registry is
  process-local, exactly like `app.state.pipeline_tasks` and the Cabin registry. A
  multi-worker fleet would move it to Redis — noted, not solved.

## Security requirements (NON-NEGOTIABLE)

- **Long-running processes stay INSIDE the gVisor Cabin.** Preview never spawns a host
  process; it always goes through `CabinService` → `CabinBackend.start_service`, so the
  app runs in the user's isolated container with their materialized secrets.
- **Deny-by-default egress + allow-list.** The Cabin's egress stays the deny-by-default
  allow-list from Phase 0b (`cabin_network_allow`, default `[]` = deny all). A preview
  binds a localhost port; it does not open egress.
- **Hard max lifetime + reaping.** No orphan processes — every preview has a hard cap and
  is reaped past it, and all previews are stopped on shutdown.
- **Per-user / owner-scoped.** A user only ever touches THEIR preview. The API is scoped
  via `get_authorized_voyage` (owner-scoped voyage) and the registry is keyed on the
  user's id — there is no path to another user's preview.
- **Secrets never surfaced.** `PreviewInfo` / `ServiceHandle` / `ServiceStatus` carry NO
  secret field. Logs are app stdout/stderr (tail) — the service never injects or echoes a
  secret, and the start command / env are never logged.
- **Lazy `aiodocker` import.** Extending `GVisorCabinBackend` must NOT import `aiodocker`
  at module top; if absent, raise a clear `CabinError`, never an opaque `ImportError`.

## Task

1. **Extend the Cabin contract** (`app/cabin/backend.py`) with long-running service
   support + new secret-free Pydantic models:
   - `ServiceStatus = Literal["starting", "running", "stopped", "failed"]`.
   - `ServiceHandle{service_id, url, port, status: ServiceStatus}` — `url` is the reachable
     preview URL; NO secret field.
   - `async start_service(user_id, command, *, env=None, port=None) -> ServiceHandle` —
     launch a long-running process in the user's Cabin, bind a port, return the handle.
   - `async service_logs(user_id, service_id, *, tail=200) -> str` — captured
     stdout/stderr tail (B1 will stream).
   - `async service_status(user_id, service_id) -> ServiceStatus`.
   - `async stop_service(user_id, service_id) -> None` (idempotent).
2. **Null backend** (`app/cabin/null_backend.py`): deterministic, in-memory long-running
   service. Stable `url` `http://127.0.0.1:<port>` (port allocated deterministically),
   canned log lines, status transitions `starting → running` on start, `stopped` on stop.
   No secret value stored or echoed. The CI default.
3. **gVisor backend** (`app/cabin/gvisor_backend.py`): real impl, lazy `aiodocker`. Start
   the process detached inside the persistent Cabin (`sh -c '<command> > logfile 2>&1 &'`
   style), tee stdout/stderr to a per-service log file, expose the bound port; egress stays
   deny-by-default + allow-list; secrets/env never logged. Opt-in only. Raise `CabinError`
   if `aiodocker` is absent.
4. **`app/services/preview_service.py`** — `PreviewService(cabin_service, settings)` +
   `PreviewError(code, message)`. Process-local per-user registry (note v1 single-worker):
   - `async start(user_id, voyage, session, *, command=None) -> PreviewInfo` — ensure the
     Cabin, resolve the command (explicit arg › `settings.preview_default_command`),
     `cabin_service`-mediated `start_service`, stamp `started_at` + the hard max lifetime,
     return `PreviewInfo{preview_id, url, status}`.
   - `async status(user_id) -> PreviewInfo | None`.
   - `async logs(user_id, *, tail=200) -> str`.
   - `async stop(user_id) -> None` (idempotent — no-op if none).
   - `async reap_expired(*, now=None) -> list` — stop previews older than
     `preview_max_lifetime_seconds` (inject `now` for tests).
   - `async stop_all()` — stop every tracked preview (shutdown).
   - `PreviewInfo` Pydantic model: `{preview_id, url, status}` — NO secret field.
5. **Settings**: `preview_default_command: str` (a generic dev-server command — document
   that real per-app detection is future), `preview_max_lifetime_seconds: int = 1800`,
   `preview_idle_timeout_seconds: int = 900` (used by the reaper if useful).
6. **App wiring** (`app/main.py`): `app.state.preview_service = PreviewService(
   cabin_service, settings)`; fold preview reaping into the existing reaper loop (or a
   sibling) so expired previews are stopped; `stop_all()` on shutdown.
7. **API** `app/api/v1/preview.py` (default-deny, owner-scoped via `get_authorized_voyage`):
   - `POST /api/v1/voyages/{id}/preview` → `PreviewInfo` (start).
   - `GET /api/v1/voyages/{id}/preview` → status (404 if none).
   - `GET /api/v1/voyages/{id}/preview/logs?tail=` → `{logs}`.
   - `DELETE /api/v1/voyages/{id}/preview` → 204 (stop).
   Register in `router.py`.

## Output format

- Type-annotated Python, async, Pydantic v2, classes PascalCase, functions snake_case,
  One Piece themed naming ("Cabin", "preview"). New artifacts only under
  `src/backend/app/`, `src/backend/tests/`, and the named pdd files.
- TDD: failing tests first, then implement to green. Null backend / mocked sessions
  (`AsyncMock`/`MagicMock`), no Docker, no Postgres.

## Constraints

- Extend the Cabin contract (ABC + Null + gVisor) for long-running services; do NOT touch
  the pipeline's `InProcessDeploymentBackend` (a standalone `PreviewService` keeps it
  untouched).
- Lazy `aiodocker` import inside methods; a missing lib → clean `CabinError`.
- In-memory registry only — NO migration (note v1 single-worker, like `pipeline_tasks`).
- Secrets never logged, never in `PreviewInfo`/`ServiceHandle`/`ServiceStatus`. Egress
  deny-by-default. Hard max lifetime + reaping (no orphans). Do NOT break existing tests.
  No git. No new dependency.

## Edge Cases

- `start` with no explicit command → uses `settings.preview_default_command`.
- `start` twice for one user → the latest preview replaces the prior (the old one is
  stopped first); ONE preview per user.
- `status`/`logs`/`stop` with no preview → `status`/`logs` empty/None, `stop` is a no-op.
- `reap_expired`: a preview older than `preview_max_lifetime_seconds` is stopped + dropped;
  a fresh one is kept. Returns the reaped preview ids (now injectable).
- gVisor `start_service` with `aiodocker` absent → `CabinError("BACKEND_UNAVAILABLE")`,
  never an opaque `ImportError`; importing the module never imports `aiodocker`.
- No secret (value) ever appears in `PreviewInfo`, a `ServiceHandle`, a log line, or an
  exception message — only app stdout/stderr (tail) is surfaced.
