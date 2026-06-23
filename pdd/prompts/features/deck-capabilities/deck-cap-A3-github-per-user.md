# Prompt: Per-user GitHub via device-flow OAuth (Phase A3)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-A3-github-per-user.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: Phase 0a — the **Sea Chest** (`SeaChestService.store`/`reveal`,
`kind="github"`), Auth (Phase 4 — `get_current_user`, default-deny middleware),
`Settings` (`GRANDLINE_` env prefix), and the existing **GitService** (per-voyage
git sandbox + `create_pr` via `api.github.com`). `httpx.AsyncClient` is available.
**Project type**: Backend (FastAPI + Pydantic v2 + SQLAlchemy async)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. Today
ALL git operations use a single deployment-level `github_api_token` and a fixed
author identity (`git_author_name`/`git_author_email`). Phase A3 lets each user
connect **their own** GitHub account via the **device-code OAuth flow** (the same
flow C0 chose for Claude Code), stores the resulting token in the **Sea Chest**
(Phase 0a), and makes user-initiated git operations (clone/push/PR) run with the
**user's** token + identity when connected — falling back to the env token
otherwise so the pipeline/Shipwright path is unchanged.

PLAN reference: PLAN-deck-capabilities.md, Workstream A → A3. Routing git execution
through the per-user **Cabin** container is a noted refinement; GitService already
sandboxes per voyage, so A3 delivers the per-user **TOKEN + identity** only.

## Security requirements (NON-NEGOTIABLE)

- **Tokens never leave the vault over the API.** No endpoint returns the access
  token. The device `poll` endpoint's `connected` status carries ONLY the GitHub
  `login` (and a `@login` label) — never the token.
- **Tokens never logged.** No access token (or `device_code`/`user_code`) in any
  log line or exception message.
- **Fixed hosts.** The device flow always talks to `github.com`
  (`/login/device/code`, `/login/oauth/access_token`); the user lookup always uses
  `settings.github_api_base_url` (`/user`). No host is ever derived from untrusted
  input.
- **client_id env-only.** `github_oauth_client_id` is a deployment setting
  (`GRANDLINE_GITHUB_OAUTH_CLIENT_ID`), never user-supplied. Unset → a clear error
  when starting the flow.
- **Default-deny + owner-scoping.** Every integration endpoint requires an
  authenticated user; the token is stored/revealed only for the requesting user.
- **Safe fallback.** When a user has not connected GitHub, git ops fall back to the
  env `github_api_token` + the configured author identity (today's behavior).

## Task

1. **GitHub auth service** (`app/services/github_auth_service.py`) —
   `GithubAuthService(session, settings)` + `GithubAuthError(code, message)`:
   - `async start_device_flow() -> DeviceFlowStart` — POST
     `https://github.com/login/device/code` with `client_id` +
     `scope=repo` (`Accept: application/json`); return
     `{user_code, verification_uri, device_code, interval, expires_in}`. Raise
     `GithubAuthError("OAUTH_NOT_CONFIGURED", …)` if `github_oauth_client_id` unset.
   - `async poll_device_flow(user_id, device_code) -> DeviceFlowStatus` — POST
     `https://github.com/login/oauth/access_token`
     (`grant_type=urn:ietf:params:oauth:grant-type:device_code`). On
     `authorization_pending`/`slow_down` → status `pending`. On success → `GET
     {api_base}/user` (Bearer) for the `login`, then
     `SeaChestService(session, settings).store(user_id, "github", access_token,
     label=f"@{login}")`; return status `connected` (login only — NO token). On
     `expired_token`/`access_denied`/other error → status `error` with the code.
   - Mirror `return_bottle_service.py`'s httpx pattern (async client, Bearer header,
     fixed host). Never log the token. `device_code`/`user_code` are transient.
   - Pydantic v2 `DeviceFlowStart` / `DeviceFlowStatus` — **no token field outbound**.
2. **GitService per-user override**: add an OPTIONAL per-user token + identity to the
   auth-using methods, default `None` (today's env behavior preserved):
   - `clone_repo(..., token: str | None = None)`
   - `commit(..., author_login: str | None = None)`
   - `push(..., token: str | None = None)`
   - `create_pr(..., token: str | None = None, author_login: str | None = None)`
   When `token` is provided it replaces `settings.github_api_token` in
   `_inject_token` / the PR Bearer header; when `author_login` is provided it
   overrides the commit/PR author identity.
3. **Wire git endpoints** (`app/api/v1/git.py`): for user-initiated `clone`/`push`/`pr`,
   resolve the caller's GitHub token via `SeaChestService(session, settings).reveal(
   user_id, "github")` and pass it (+ the `@login` identity from the credential
   label) to GitService; if not connected, pass `None` (env fallback). Keep
   owner-scoping (`get_authorized_voyage`).
4. **Integrations API** (`app/api/v1/integrations.py`, kebab `/api/v1/integrations`,
   default-deny via `get_current_user`, per-user):
   - `POST /integrations/github/device/start` → `DeviceFlowStart`.
   - `POST /integrations/github/device/poll` body `{device_code}` →
     `DeviceFlowStatus` (`pending`/`connected`/`error`; stores on success).
   Register the router in `router.py`.
5. **Settings**: `github_oauth_client_id: str = ""`
   (env `GRANDLINE_GITHUB_OAUTH_CLIENT_ID`).

## Output format

- Type-annotated Python, async, Pydantic v2, classes PascalCase, functions
  snake_case, One Piece themed naming. New artifacts only under `src/backend/app/`,
  `src/backend/tests/`, and the named pdd files.
- TDD: failing tests first, then implement to green. Mocked httpx + sessions
  (`AsyncMock`/`MagicMock`), no Postgres, no real GitHub.

## Constraints

- Mirror `return_bottle_service.py` (httpx Bearer, fixed host) and the Sea Chest
  trio (owner-scoped, `Error(code, message)`).
- No new dependency (httpx exists). No Alembic migration (the Sea Chest table
  already holds `kind="github"`). Do NOT break existing tests. No git.

## Edge Cases

- `github_oauth_client_id` unset → `start_device_flow` raises `OAUTH_NOT_CONFIGURED`.
- `poll` while the user hasn't approved → `authorization_pending`/`slow_down` →
  status `pending` (no store).
- `poll` after approval → `/user` login fetched, token stored under `@login`, status
  `connected` carrying ONLY the login (never the token).
- `poll` after expiry/denial → status `error` (no store).
- A connected user's clone/push/PR uses THEIR token in `_inject_token`/the Bearer
  header and THEIR identity as author; a non-connected user falls back to the env
  token + configured identity.
- No endpoint, status, or log line ever exposes the access token / `device_code` /
  `user_code`.
