# Prompt: Per-user Claude Code via device-login in the Cabin (Phase C0)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-C0-claude-connect.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: Phase 0a — the **Sea Chest** (`SeaChestService.store`/`reveal`,
`kind="claude_code"`), Phase 0b — the **Cabin** (`CabinService.ensure`/`run`), Auth
(Phase 4 — `get_current_user`, default-deny middleware), `Settings` (`GRANDLINE_` env
prefix), and the existing **`claude_code` dial adapter** (runs the Claude CLI in
`--print` mode). Mirrors the SAME shape as A3 (per-user GitHub via device flow).
**Project type**: Backend (FastAPI + Pydantic v2 + SQLAlchemy async) + Frontend
(Next.js / React / TS, React Query).

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. Today the
`claude_code` adapter runs the Claude CLI with the HOST's credentials (a single
`claude` login / `CLAUDE_CODE_OAUTH_TOKEN` / API key in the backend process env). C0
lets each user connect **their own** Claude Code account: a device-login flow is run
INSIDE the user's **Cabin** (Phase 0b), the captured `CLAUDE_CODE_OAUTH_TOKEN` is
vaulted in the **Sea Chest** (Phase 0a, `kind="claude_code"`), and the `claude_code`
adapter then sets `CLAUDE_CODE_OAUTH_TOKEN` from that per-user credential so the CLI
runs AS THE USER. Absent a connected credential, the host behavior is unchanged.

PLAN reference: PLAN-deck-capabilities.md, Workstream C → C0. Mirror how A3 scoped the
GitHub equivalent: deliver the per-user **token** now (the adapter sets
`CLAUDE_CODE_OAUTH_TOKEN` from the user's Sea Chest credential); routing the FULL CLI
execution inside the Cabin is a **noted refinement**.

## Security requirements (NON-NEGOTIABLE)

- **The token never leaves the vault over the API.** No endpoint returns the captured
  `CLAUDE_CODE_OAUTH_TOKEN`. `ClaudeLoginStatus` carries ONLY a
  `connected`/`pending`/`error` status + a non-secret `label`.
- **The token is never logged.** No token (or raw CLI output that might carry one) in
  any log line or exception message. The in-flight login registry holds the captured
  token process-locally and wipes it the moment it is vaulted.
- **Fixed verification host shape.** The verification URL parsed from CLI output is
  anchored to the Anthropic/Claude host family — never derived from arbitrary input.
- **Default-deny + owner-scoping.** Every integration endpoint requires an
  authenticated user; the login is owner-scoped (a user cannot poll another's login)
  and the token is stored/revealed only for the requesting user.
- **Safe fallback.** When a user has not connected Claude Code, the adapter, the
  factory/router, and the dependency all default to today's host behavior (the token
  is used ONLY when present; absent → unchanged).

## Task

1. **Claude auth service** (`app/services/claude_auth_service.py`) —
   `ClaudeAuthService(session, settings, cabin_service=None)` + `ClaudeAuthError(code,
   message)`:
   - `async start_login(user_id) -> ClaudeLoginStart` — run
     `settings.claude_code_login_command` (default `claude setup-token`) INSIDE the
     user's Cabin via `CabinService.run`, parse the verification URL (+ optional short
     user code) from the output, mint an opaque `login_id`, remember the run, and
     return `{verification_uri, user_code?, login_id}`. `CABIN_UNAVAILABLE` when no
     Cabin runner is wired; `LOGIN_FAILED` when no URL can be parsed (never echo raw
     output).
   - `async poll_login(user_id, login_id) -> ClaudeLoginStatus` — owner-scoped lookup
     of the in-flight login; if the token was captured (from the start run or a
     re-run of the idempotent login command), `SeaChestService.store(user_id,
     "claude_code", token, label="claude-login")` → `connected` (label only); else
     `pending`; unknown/foreign `login_id` → `error` (`unknown_login`). Token never
     returned or logged.
   - Pydantic v2 `ClaudeLoginStart`/`ClaudeLoginPollRequest`/`ClaudeLoginStatus`
     (`extra="forbid"`, **no token field outbound**).
   - HONEST CAVEAT (in the docstring): the EXACT Claude CLI device-flow mechanics need
     the real CLI; the service is structured around the flow and FULLY unit-tested
     with the Cabin run MOCKED. The login command is a setting so deployments pin it.
2. **Adapter per-user token**: `ClaudeCodeAdapter.__init__(..., oauth_token: str |
   None = None)`; in `_env`, set `env["CLAUDE_CODE_OAUTH_TOKEN"] = self._oauth_token`
   when present (else leave host behavior). Thread `oauth_token` through
   `create_adapter` + `build_router_from_config` (default `None`, applied only to
   `claude_code`/`claude-code` adapters), and resolve it from the Sea Chest in
   `get_dial_router` (reveal the voyage OWNER's `claude_code` credential).
3. **Integrations API** (`app/api/v1/integrations.py`, kebab `/api/v1/integrations`,
   default-deny via `get_current_user`, per-user):
   - `POST /claude/login/start` → `ClaudeLoginStart`.
   - `POST /claude/login/poll` body `{login_id}` → `ClaudeLoginStatus`
     (`CABIN_UNAVAILABLE` → 503, other `ClaudeAuthError` → 502). The Cabin runner is
     resolved from `app.state.cabin_service`.
4. **Settings**: `claude_code_login_command: str = "claude setup-token"` (env
   `GRANDLINE_CLAUDE_CODE_LOGIN_COMMAND`).
5. **Frontend**: make the `claude_code` **Connect** in `DialPanel` real — start →
   show the verification URL/code (user opens it) → poll until `connected`, then
   invalidate `["sea-chest"]` so the status flips to Connected. GitHub's Connect stays
   "coming soon". New `lib/integrations.ts` + a `useClaudeLogin` hook; loading/error
   states on every async surface.

## Output format

- Type-annotated Python, async, Pydantic v2; classes PascalCase, functions
  snake_case; One Piece themed naming. New artifacts only under `src/backend/app/`,
  `src/backend/tests/`, `src/frontend/`, and the named pdd files.
- TDD: failing tests first, then implement to green. Mocked Cabin run + sessions
  (`AsyncMock`/`MagicMock`), no Postgres, no real CLI, no container.

## Constraints

- Additive + fallback-safe: NO behavior change when no per-user credential. Do NOT
  break `test_dial_claude_code_adapter.py`, `test_dial_factory.py`,
  `test_dial_router.py`. Mirror `github_auth_service.py` + the Sea Chest trio
  (owner-scoped, `Error(code, message)`). No new dependency. No Alembic migration (the
  Sea Chest table already holds `kind="claude_code"`). No git.

## Edge Cases

- No Cabin runner wired → `start_login` raises `CABIN_UNAVAILABLE`.
- Cabin output has no verification URL → `LOGIN_FAILED` (raw output never echoed).
- `poll` before approval → `pending` (no store).
- `poll` after approval → token captured, vaulted under `label="claude-login"`,
  `connected` (label only — never the token).
- `poll` with an unknown or another user's `login_id` → `error` (`unknown_login`).
- Adapter with no `oauth_token` (the default) → `CLAUDE_CODE_OAUTH_TOKEN` is NOT set
  by the adapter (host behavior preserved).
- No endpoint, status, or log line ever exposes the captured token.
