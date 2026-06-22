# Project: GrandLine

**Last updated**: 2026-06-22

## What we're building
A web-based multi-agent orchestration platform where a crew of persona-based AI agents voyage together through a structured pipeline to build, test, and deploy software solutions. Themed after One Piece — the crew, the voyage, and the platform vocabulary are all drawn from that world.

Users chart a course (submit a task). The crew decomposes, plans, tests, builds, validates, and deploys — autonomously, but always under the user's authority as fleet admiral.

PDD and TDD aren't optional flags — they're the Log Pose. Without them, the crew doesn't sail.

## Who it's for
- Developers and teams who want an AI crew that follows a disciplined engineering pipeline (PDD → TDD → Implement → Review → Deploy)
- Engineers who need observable, interventable multi-agent execution with real-time visibility
- Organizations that want provider-agnostic AI orchestration with failover and state preservation

## The Crew (Agent Personas)

| Agent | Role | Responsibility |
|---|---|---|
| **Captain** | Project Manager | Decomposes user tasks into a voyage plan. Assigns work to crew. Manages priorities and sequencing. |
| **Navigator** | Architect | Drafts the Poneglyphs (PDD prompt artifacts) — the encoded instructions that guide every step. Makes technical design decisions. |
| **Shipwrights** | Developers | Build the actual code. Follow Poneglyphs precisely. Work on per-agent git branches. |
| **Doctor** | QA Engineer | Writes health checks (tests) BEFORE any code is written (TDD). Validates after Shipwrights build. |
| **Helmsman** | DevOps Engineer | Handles deployment across three tiers. Manages containers, pipelines, and infrastructure. |

## The Voyage Pipeline
Every task flows through this structured pipeline — no shortcuts:

```
Chart Course → Captain Plans → Navigator Writes Poneglyphs (PDD)
  → Doctor Writes Health Checks (TDD) → Shipwrights Build
  → Doctor Validates → Helmsman Deploys
```

## Observation Deck (Real-time War Room UI)
The dashboard where users watch the voyage unfold. Three views:

| View | Name | What it shows |
|---|---|---|
| **Sea Chart** | Board View | Tasks flowing through waters: PDD → TDD → Implement → Review → Deployed |
| **Crew Map** | Graph View | Live DAG showing agents communicating via Den Den Mushi (message bus) |
| **Ship's Log** | Timeline View | Chronological record of every agent action, filterable by crew member |

Users can intervene at any point — pause an agent, redirect work, inject context — like a fleet admiral overseeing the voyage.

## One Piece Vocabulary Map

| Platform concept | One Piece term | Description |
|---|---|---|
| PDD prompt artifacts | **Poneglyphs** | Encoded instructions that guide every step |
| PDD + TDD methodology | **Log Pose** | The navigation system — without it, the crew doesn't sail |
| LLM gateway | **Dial System** | Routes calls across providers with config-driven role mapping |
| State checkpoints | **Vivre Cards** | Snapshots of agent state for failover — no work is lost |
| Message bus | **Den Den Mushi** | Inter-agent communication system (Redis Streams) |
| Dashboard | **Observation Deck** | Real-time war room UI |
| Task submission | **Chart a Course** | User submits a task to the crew |
| Implementation plan | **Voyage Plan** | Captain's decomposed task plan |
| Cross-voyage memory | **Log Book** | Per-repo prior knowledge the Captain recalls at planning time — the crew never re-explains the stack |
| Reusable voyage presets | **Standing Orders** | Named bundles of dial config + plan skeleton + injected context + default repo — recurring task shapes chart in one call |
| External triggers | **Message in a Bottle** | A signature-verified inbound GitHub webhook charts a course from an issue, recording origin metadata for the return trip |
| Completion write-back | **Return Bottle** | On voyage completion, posts a summary back to the originating GitHub issue (Phase 21 `origin`) and records a per-repo Log Book summary — best-effort, never fails the voyage |
| Lossless per-voyage deck state + quick voyage switcher | **Fleet Switcher** | Each voyage remembers its own deck UI state (last view, Ship's Log filters, group-by-phase, scroll), persisted per-voyage in versioned localStorage so switching is lossless; the Fleet Switcher overlay (`g f` / header / palette) hops between concurrent voyages and lands you back where you left |
| Browser-in-the-loop verification | **Bedside Browser** | The Doctor drives a headless browser against a running app, asserts the page renders, and surfaces a screenshot in the Ship's Log — "tests pass AND the page renders". Behind a swappable `BrowserCheckBackend` (Null default, Playwright opt-in) |

## Tech stack
- **Language**: TypeScript (frontend), Python (backend)
- **Frontend**: Next.js 14+ (App Router), React, Tailwind CSS, shadcn/ui
- **State management**: Zustand (client state), React Query / TanStack Query (server state)
- **Animations**: Framer Motion (landing page), Three.js / React Three Fiber (optional 3D visuals)
- **Backend**: Python, FastAPI (async)
- **AI/Agent framework**: LangGraph (multi-agent orchestration)
- **LLM providers**: Multi-provider (Anthropic, OpenAI, local models) — config-driven role mapping via Dial System
- **Database**: PostgreSQL (JSONB for agent metadata, Vivre Card state)
- **ORM**: SQLAlchemy + Alembic (migrations)
- **Message bus**: Redis Streams (Den Den Mushi — inter-agent communication, real-time events)
- **Deployment**: Docker Compose (local dev, local-first), Kubernetes + Helm (production)
- **CI/CD**: GitHub Actions
- **Docs**: Auto-generated under `docs/`, hosted on GitHub Pages

## Framework & rendering
- Framework: Next.js 14+ (App Router)
- Rendering strategy: Hybrid — SSG for public landing page (`/`, `/features`), CSR for Observation Deck (`/app/*`)
- Deployment target: Docker Compose (local-first), Kubernetes (production)

## API design
- Style: REST (CRUD) + SSE (LLM token streaming, agent output) + WebSockets (bidirectional — user intervention, live Observation Deck)
- Versioning: `/api/v1/` prefix
- Auth method: JWT + API keys, default-deny at middleware level
- API spec: OpenAPI / Swagger (auto-generated by FastAPI)

## Data layer
- Primary database: PostgreSQL
- ORM: SQLAlchemy
- Migration tool: Alembic
- Message bus: Redis Streams (Den Den Mushi)
- State persistence: Vivre Card snapshots in PostgreSQL

## Auth
- **Default-deny** at middleware level — no route is open unless explicitly allowed
- JWT-based authentication
- Session storage: Redis-backed sessions
- Protected routes: Middleware-level enforcement

## Dial System (LLM Gateway)
- Provider-agnostic: Anthropic, OpenAI, Ollama (local models)
- Config-driven role mapping: each agent persona mapped to a provider/model via DialConfig JSONB
- Adapter pattern: `ProviderAdapter` ABC with `complete()`, `stream()`, `check_rate_limit()`
- Adapter factory: `create_adapter()` + `build_router_from_config()` — no global instances, created per-request
- Failover: `DialSystemRouter` checks rate limits, tries primary, falls back through chain on `ProviderError`
- Failover applies to both `route()` (sync completion) and `stream()` (SSE streaming)
- Rate limiter: Redis sliding-window sorted sets tracking tokens + requests per provider
- SSE streaming: `POST /completions/stream` returns `text/event-stream` with `data: {token}\n\n` format
- `ProviderSwitchedEvent` published via Den Den Mushi on failover

## Agent Execution
- Agents work in **real git repos** with **per-agent branches**
- Agents execute in **sandboxed containers** — isolated, secure
- Agent state is persisted to PostgreSQL (Vivre Cards) for resumability
- Inter-agent communication via Redis Streams (Den Den Mushi)
- All agent executions are logged for observability (Ship's Log)

## Deployment Tiers

| Tier | Name | Trigger | Approval |
|---|---|---|---|
| Preview | Auto-preview | Automatic on branch push | None |
| Staging | Semi-auto | Automatic on PR merge to staging | Lightweight review |
| Production | PR-only | PR merge to main | Full review required |

## What good output looks like
- Clean, typed code with no `any` types
- Every feature has tests before implementation (TDD — the Doctor writes health checks first)
- Every feature goes through PDD workflow (Navigator writes Poneglyphs first)
- Documentation auto-updates with code changes
- All API endpoints documented via OpenAPI
- Agent workflows are observable end-to-end via the Observation Deck
- One Piece terminology used consistently throughout the codebase

## Constraints (what the AI should never do or suggest)
- Never skip writing tests — TDD is the Log Pose
- Never bypass PDD workflow — Poneglyphs guide every step
- Never hardcode LLM API keys or secrets in source code
- Never use `any` type in TypeScript
- Never put artifacts outside the `src/` directory structure
- Never make direct changes to `main` — all changes go through PRs
- Never skip documentation updates when features change
- Never allow agent execution outside sandboxed containers
- Never lose work — Vivre Card checkpointing is mandatory for provider failover

## Current state
Phases 1-10 complete. The backend is functional with:
- **Phase 1-2**: Docker infrastructure, PostgreSQL + Redis, SQLAlchemy models (Voyage, VoyagePlan, Poneglyph, VivreCard, CrewAction, DialConfig)
- **Phase 3**: Pydantic schemas for all models, DialConfig with JSONB role_mapping/fallback_chain
- **Phase 4**: JWT auth (register, login, refresh, logout) with default-deny middleware
- **Phase 5**: Den Den Mushi message bus (Redis Streams) with consumer groups, dead-letter handling, xautoclaim stale recovery
- **Phase 6**: Dial System LLM gateway — provider adapters (Anthropic, OpenAI, Ollama), adapter factory, role-based routing with failover, Redis sliding-window rate limiter, SSE streaming endpoint
- **Phase 7**: Vivre Card state checkpointing — service, API, and Dial System hook for provider failover
- **Phase 8**: Execution Service — containerized sandbox with gVisor/Docker backend (aiodocker), swappable ExecutionBackend ABC, per-user sandbox lifecycle, path traversal sanitization, file size limits, app lifespan wiring
- **Phase 9**: Git Integration Service — per-voyage sandboxed git operations (clone, branch, commit, diff, log), host allowlist to prevent token exfiltration, NUL-delimited git output parsing, branch creation from `origin/<base>` for freshness
- **Phase 10**: Captain Agent — first crew member implemented. LangGraph two-node graph (decompose → validate) for task-to-plan decomposition via Dial System. CaptainService with atomic plan + VivreCard persistence, replannable status lifecycle, best-effort event publishing. VoyagePlanSpec with dependency graph validation (unique phases, valid references, cycle detection via topological sort). REST endpoints: POST/GET `/voyages/{id}/plan`
- **Phase 19**: Log Book — per-repo cross-voyage memory. `LogBookEntry` model (`log_book_entries`, keyed on `target_repo`), `LogBookService` (`record`/`recall`/`render_context`), and REST endpoints `GET`/`POST /api/v1/log-book` (default-deny). `CaptainService.chart_course` recalls prior knowledge for `voyage.target_repo` and best-effort prepends it to the planning task, so the crew never re-explains a repo's layout/conventions/gotchas. Writes are API-driven; auto write-back from completed voyages is a noted follow-up.
- **Phase 20**: Standing Orders — reusable voyage presets. `StandingOrder` model (`standing_orders`, per-user, unique `(user_id, name)`) bundling `{dial_config + plan_skeleton + injected_context + target_repo}`. `StandingOrderService` provides owner-scoped CRUD plus `chart(...)`, which stamps a `CHARTED` voyage the same way `voyages.py` does but seeds its `DialConfig` from the preset (else the shared default) and prepends `injected_context` to the voyage description. REST endpoints at `/api/v1/standing-orders` (collection + item + `POST /{id}/chart` -> `VoyageRead`, default-deny, `NOT_FOUND` -> 404). Recurring task shapes ("bugfix voyage", "dep-bump voyage") chart in one call. Materializing `plan_skeleton` into a `VoyagePlan` is a noted follow-up.
- **Phase 21**: Message in a Bottle — external triggers. A signature-verified inbound GitHub `issues` webhook charts a course from an issue. New nullable `origin` JSONB column on `Voyage` records the canonical provenance (`{type, repo, issue_number, issue_url, issue_title, sender, received_at}`; NULL for manually-charted voyages) — the seam Phase 22 "Return Bottle" reads to reply back. `TriggerService` exposes constant-time HMAC-SHA256 signature verification (`X-Hub-Signature-256`), action+label gating (`should_trigger`), config-resolved owning user (`trigger_default_user_email`), and `ingest_github_issue` which reuses `voyages._default_dial_config` so a triggered voyage is configured identically to a manual one. `POST /api/v1/triggers/github` is the single deliberate default-deny relaxation: no Bearer token, HMAC-verified (401 on bad/unconfigured signature), 200 `ignored` for non-trigger events, 201 `charted` on success. Settings (env only): `github_webhook_secret`, `trigger_default_user_email`, `trigger_label` (default `"grandline"`).
- **Phase 23**: Bedside Browser — browser-in-the-loop verification. The Doctor drives a headless browser against a running app, asserts the page renders, and surfaces a screenshot in the Ship's Log ("tests pass AND the page renders"). Browser execution sits behind a swappable `BrowserCheckBackend` ABC selected by `create_browser_backend(settings)` (env `GRANDLINE_BROWSER_BACKEND`), mirroring `ExecutionBackend`/`DeploymentBackend`: the v1 default `NullBrowserBackend` is deterministic and browser-free (CI-safe, the analogue of `InProcessDeploymentBackend`); `PlaywrightBrowserBackend` is opt-in and lazily imports Playwright inside `run` (raising `BrowserBackendError` if absent) so app startup and the test suite never require it. Playwright is NOT in `requirements.txt` (opt-in install). New `BrowserCheck` model (`browser_checks`, migration `b8d4f2a6c1e3`). `BedsideBrowserService.run_browser_check(voyage, phase_number, spec, backend)` persists the result and records a `BROWSER_CHECK_RUN` CrewAction carrying the `screenshot_ref` so the Ship's Log surfaces the screenshot. API (default-deny, owner-scoped): `POST /api/v1/voyages/{id}/phases/{phase_number}/browser-check` -> 201, `GET /api/v1/voyages/{id}/browser-checks`.
- **Phase 22**: Return Bottle — close the loop. On a successful pipeline run, a best-effort completion-time write-back (AFTER the `PIPELINE_COMPLETED` commit in `PipelineService.start`) (a) posts a themed voyage summary back as a comment on the originating GitHub issue using the Phase 21 `origin`, and (b) records a per-repo Log Book `summary` entry so future voyages recall the outcome — satisfying the Phase 19 deferred auto write-back. `ReturnBottleService(session, settings)` exposes pure `build_summary`, `post_to_github_issue` (fixed host `github_api_base_url`, reuses `github_api_token`, never derived from `origin`), and `report` returning `{"issue_commented", "log_book_recorded"}`. A Return Bottle failure (httpx/DB error, malformed `origin`) is swallowed + logged and NEVER fails or rolls back the completed voyage. Manual re-send via `POST /api/v1/voyages/{id}/return-bottle` (default-deny, owner-scoped, 409 `VOYAGE_NOT_COMPLETED` for a non-completed voyage). New setting `github_api_base_url` (default `https://api.github.com`, env only). No migration.

- **Phase 24**: Fleet Switcher — multi-voyage deck (frontend). Deck UI state was GLOBAL and bled across voyages on switch; it is now **per-voyage and lossless**. New sibling Zustand store `stores/deckState.ts` keyed by `voyageId` holds `{lastView, logFilters, groupByPhase, scroll}` with sane defaults for unknown voyages, persisted to versioned localStorage (`DECK_STATE_VERSION`, reusing the `readPref`/`writePref` helper, SSR-guarded). It layers on TOP of `stores/voyage.ts` — `selectVoyage(id)` stays the single switch primitive (it owns the per-voyage event ring + LRU `visitedOrder`); deck UI state is tiny and is NOT LRU-evicted, so switching back is always lossless. The **Fleet Switcher** (`components/observation-deck/FleetSwitcher.tsx`) is a Command-Palette-consistent overlay (header "⛵ Fleet" button, palette entry, `g f` chord through the existing editable-focus guard) that lists voyages (`useVoyages`, recents-first, title + `StatusBadge`), calls `selectVoyage(id)`, and navigates to that voyage's restored `lastView`. Ship's Log was rewired off its old global `logFilters` pref onto the per-voyage store and now restores/saves scroll per voyage; a `useTrackDeckView(view)` hook records `lastView` per voyage from each view.

- **Phase C1**: Per-role claude_code options — a voyage can set the `claude_code` provider's `max_turns` PER ROLE inside its `role_mapping` entry, instead of only via the global env `Settings.claude_code_max_turns`. Mirrors the `ShipwrightRoleConfig.max_concurrency` precedent: new strict `ClaudeCodeRoleConfig{max_turns: int|None, ge=1, le=10}` + defensive `resolve_claude_code_role_config(role_cfg)` (validates a filtered subset so sibling `provider`/`model` keys are tolerated; returns all-None defaults + logs a warning on any non-dict/invalid shape) in `app/schemas/dial_config.py`. `factory.create_adapter` gained an optional `role_cfg=None`; its claude_code branch resolves `max_turns = resolve_claude_code_role_config(role_cfg).max_turns or settings.claude_code_max_turns` and `build_router_from_config` passes the role's raw mapping entry. **Safe behavioral knob only** — host/auth knobs (`cli_path`/`workspace`/`extra_args`/tokens) stay env-level. The DialPanel UI is C2; per-user Claude Code credentials are C0 (both out of scope here).

- **Phase 0a**: Sea Chest — the encrypted per-user credential vault (storage half of Phase 0 Cabin + Sea Chest; the credential substrate A3 per-user GitHub / C0 device-login Claude Code / the Cabin consume later). New `UserCredential` model (`user_credentials`, migration `c1d2e3f4a5b6`) storing ONLY the encrypted secret (`ciphertext` BYTEA — no plaintext column) plus non-secret metadata (`kind` `"claude_code"`/`"github"`, `label` hint, timestamps, `last_used_at`), unique `(user_id, kind)`. `app/core/seachest_crypto.py` derives a Fernet key from `Settings.seachest_key` (env `GRANDLINE_SEACHEST_KEY`; arbitrary string → SHA-256 → urlsafe-b64, or an already-valid key as-is) and `encrypt`/`decrypt`s; unset key + `debug` derives a STABLE dev key with a warning, unset + non-debug raises `SeaChestKeyError` (fail closed, mirroring `validate_production_settings`). `SeaChestService(session, settings)` is owner-scoped: `store` (encrypt + upsert, returns secret-free `CredentialStatus`), `reveal` (decrypt for INTERNAL consumers only — not API), `status`/`status_for`, `delete`. API (default-deny, owner-scoped, kebab `/api/v1/sea-chest`): `GET` (statuses, no secrets), `PUT /{kind}` (store/replace), `DELETE /{kind}` (204). The API exposes STATUS only — never the secret or ciphertext. New setting `seachest_key`. The Cabin half (per-user container + secret injection) is out of scope here.

- **Phase 0b**: Cabin — the per-user persistent sandbox container (runtime half of Phase 0 Cabin + Sea Chest). A Cabin is a persistent, per-user, isolated container that holds the user's credentials (materialized from the Sea Chest) and will later run their workloads (C0 device-login Claude Code, A3 git ops, B0–B3 preview + terminal); this phase delivers lifecycle + secret materialization + idle reaper only. New `app/cabin/` package mirrors the `ExecutionBackend`/`DeploymentBackend`/`BrowserCheckBackend` swap: `CabinBackend` ABC + `CabinError` (`ensure(user_id, *, secrets, network_allow)` materializes secrets by kind INSIDE the container + applies a deny-by-default egress allow-list, `run`/`status`/`destroy`/`close`); secret-free `CabinInfo`/`CabinStatus`/`CabinRunResult`. The v1 default `NullCabinBackend` is deterministic, in-memory, container-free (CI-safe, the analogue of `InProcessDeploymentBackend`) and records only the KINDS materialized, never the secret values; `GVisorCabinBackend` is opt-in and **lazily imports `aiodocker` inside its methods** (clean `CabinError` if absent — startup + tests never need Docker), reusing the gVisor isolation but persistent-per-user with `NetworkMode: none` unless hosts are allow-listed. `create_cabin_backend(settings)` selects on `cabin_backend` (default `"null"`, `"gvisor"` opt-in, unknown -> `ValueError`). `CabinService(backend, settings)` keeps a process-local per-user registry (v1 single-worker, like `pipeline_tasks`): `ensure(user_id, session)` reveals the user's Sea Chest secrets and passes them to the backend; `reap_idle(*, now=None)` destroys Cabins idle past `cabin_idle_timeout_seconds` OR older than `cabin_max_lifetime_seconds`. `app/main.py` constructs `app.state.cabin_service` and spawns a background reaper task (cancelled + awaited on shutdown, mirroring the pipeline drain). API (default-deny, per-user): `GET`/`POST`/`DELETE /api/v1/cabin` — status carries no secret. New settings `cabin_backend`/`cabin_idle_timeout_seconds`/`cabin_max_lifetime_seconds`/`cabin_reap_interval_seconds`/`cabin_network_allow`. No migration (in-memory registry).

- **Phase A2**: Real git diffs in the Changes view — TRUE before/after (base ↔ the crew's branch) on top of A1's artifact browser. Three new `GitService` methods mirror the per-voyage sandbox-exec pattern (validated argv, `GitError`): `list_changed_files` (`git diff --name-status base...head` → `GitChangedFile{path, status}`), `diff` (`git diff base...head [-- path]` → `GitDiff{base, head, path, unified}`), `get_file_content` (`git show ref:path` → `GitFileContent{ref, path, content}`). Refs use the existing `BRANCH_NAME_RE`; a new `_validate_repo_path` rejects `..`/absolute/`~` paths (traversal/injection defense). New owner-scoped `GET /voyages/{id}/git/changed-files|diff|file-content` (via `get_authorized_voyage`, `_handle_git_error` with `INVALID_PATH`→400). Frontend `hooks/useGitDiff.ts` discovers the crew's head branch from `/git/branches` (first `agent/*`, else current non-`main`, else null) so `ChangesPanel`'s `{voyageId}` contract is unchanged, then reads changed-files + diff; `ChangesPanel` gained a **Files | Diff** mode toggle (Diff = changed-file list + unified diff via `prism-react-renderer`'s `diff` language with added/removed line tint). When a voyage has no crew branch / git is absent, Diff mode **falls back to the A1 Files view**. No migration, no new dependency.

- **Phase C2**: DialPanel UI — the deck's Details-drawer **Dial** tab now surfaces the C1 + Phase 0a backends. A per-role **`max_turns`** number input (1–10, optional) appears only for `claude_code` rows and saves inside the existing `role_mapping` PUT (`RoleProviderConfig` gained `max_turns?: number`; a stray value never trips the provider+model save guard). **Fallback chains became editable** — per-role add/remove of `{provider, model?}` entries held in a `fallbackDraft`, saved together with `role_mapping` via the same `updateDialConfig(voyageId, { role_mapping, fallback_chain })` call + Save button (replacing the old read-only display). A new **Sea Chest connection status** section (`useSeaChest` hook over `GET /api/v1/sea-chest`, `CredentialStatusRow`) shows `claude_code` / `github` as Connected (with the non-secret `label`) or Not connected, with a **Disconnect** action (`DELETE /api/v1/sea-chest/{kind}`) and a disabled **"Connect (coming soon)"** affordance — the connect flows are C0 (device-login) and A3 (GitHub OAuth). New `lib/seaChest.ts` + `hooks/useSeaChest.ts`. Never renders a secret (the API doesn't return one). No backend change, no new dependency.

- **Phase A3**: Per-user GitHub via device-flow OAuth — each user connects THEIR OWN GitHub through GitHub's device-code flow (consistent with C0's Claude choice), the token lands in the Sea Chest (`kind="github"`), and user-initiated git ops run with the user's token + identity when connected, falling back to the env `github_api_token` + configured author identity otherwise (the pipeline/Shipwright path is unchanged). New `GithubAuthService(session, settings)` + `GithubAuthError(code, message)` mirrors the Return Bottle httpx pattern (async client, fixed hosts): `start_device_flow` POSTs `github.com/login/device/code` (`client_id` + `scope=repo`) → `DeviceFlowStart{user_code, verification_uri, device_code, interval, expires_in}` (raises `OAUTH_NOT_CONFIGURED` when `github_oauth_client_id` unset); `poll_device_flow(user_id, device_code)` POSTs `github.com/login/oauth/access_token` (`authorization_pending`/`slow_down`→`pending`), on success fetches the login via `GET {api_base}/user` and `SeaChestService.store(user_id, "github", token, label="@login")` → `DeviceFlowStatus{status, login}` (`connected` carries the login ONLY — never the token), on `expired_token`/`access_denied`→`error`. `GitService` gained OPTIONAL per-user overrides (default `None` = env behavior preserved): `clone_repo(..., token=None)`, `commit(..., author_login=None)`, `push(..., token=None)`, `create_pr(..., token=None, author_login=None)` — a provided token overrides the env token in `_inject_token`/the PR Bearer header and the login overrides the commit/PR author identity. The git endpoints (`clone`/`push`/`pr`) resolve the caller's token + `@login` from the Sea Chest (`get_github_identity`) and pass them through; not connected → env fallback. New default-deny, owner-scoped integrations API (`app/api/v1/integrations.py`, `/api/v1/integrations`): `POST /github/device/start` → `DeviceFlowStart`, `POST /github/device/poll` `{device_code}` → `DeviceFlowStatus` (stores on success). No endpoint returns the token. New setting `github_oauth_client_id` (env only). Routing git execution through the per-user Cabin container is a noted refinement (A3 delivers the per-user TOKEN + identity; GitService already sandboxes per voyage). No migration (the Sea Chest table already holds `kind="github"`), no new dependency.

- **Phase C0**: Per-user Claude Code via device-login in the Cabin — each user connects THEIR OWN Claude Code account through a device-login run INSIDE their **Cabin** (Phase 0b); the captured `CLAUDE_CODE_OAUTH_TOKEN` is vaulted in the Sea Chest (`kind="claude_code"`) and the `claude_code` adapter then runs the CLI **as the user** by setting `CLAUDE_CODE_OAUTH_TOKEN` from that credential — falling back to today's host auth when not connected (additive + fallback-safe; the existing dial path is unchanged). New `ClaudeAuthService(session, settings, cabin_service=None)` + `ClaudeAuthError(code, message)` mirrors A3's shape: `start_login(user_id)` runs `settings.claude_code_login_command` (default `claude setup-token`) via `CabinService.run`, parses the verification URL (+ optional user code) and returns `ClaudeLoginStart{verification_uri, user_code?, login_id}` (`CABIN_UNAVAILABLE` with no Cabin runner, `LOGIN_FAILED` when no URL parses — raw output never echoed); `poll_login(user_id, login_id)` is owner-scoped, captures the token from the start run or an idempotent re-run, and on success `SeaChestService.store(user_id, "claude_code", token, label="claude-login")` → `ClaudeLoginStatus{status, label}` (`connected`/`pending`/`error` — never the token), with an in-flight process-local registry that wipes the token the instant it is vaulted. `ClaudeCodeAdapter` gained an optional `oauth_token` (set in `_env` only when present); `create_adapter`/`build_router_from_config` thread it into `claude_code` adapters only; `get_dial_router` reveals the voyage OWNER's `claude_code` credential and passes it (None → host behavior). API (default-deny, owner-scoped, Cabin runner from `app.state.cabin_service`): `POST /api/v1/integrations/claude/login/start` → `ClaudeLoginStart`, `POST /api/v1/integrations/claude/login/poll` `{login_id}` → `ClaudeLoginStatus` (`CABIN_UNAVAILABLE`→503, other→502). New setting `claude_code_login_command` (env only). HONEST CAVEAT: the exact Claude CLI device-flow mechanics need the real CLI — the service is structured + fully unit-tested with the Cabin run mocked, and routing the FULL CLI execution inside the Cabin is a noted refinement (C0 delivers the per-user token). No migration (the Sea Chest table already holds `kind="claude_code"`), no new dependency.

**Frontend** (Observation Deck, Next.js App Router + React + Tailwind + Zustand + TanStack Query): the deck is implemented — Sea Chart / Crew Map / Ship's Log views, a multi-voyage event store with replay→live cutover and LRU buffering, WS/SSE streaming, playback, intervention controls, command palette + keyboard shortcuts, (Phase 24) the Fleet Switcher with lossless per-voyage deck state, and the Details-drawer **Changes** tab — (Phase A1) an artifact-based, always-available code browser (built files grouped by phase, syntax-highlighted via `prism-react-renderer`) with (Phase A2) a **Diff** mode showing real git diffs (changed files + unified diff, base ↔ the crew's branch) that falls back to the A1 artifacts view when a voyage didn't use git, and the Details-drawer **Dial** tab — (Phase C2) editing role→provider/model with a per-role `claude_code` `max_turns` knob, editable fallback chains, and a Sea Chest connection status panel (Connected/Disconnect) where (Phase C0) the `claude_code` **Connect** is now a real device-login flow (start → show the verification URL/code → poll until connected, then invalidate `["sea-chest"]`) via `lib/integrations.ts` + `hooks/useClaudeLogin.ts`, while GitHub's Connect stays "coming soon" — never rendering a secret.

## Source directory structure
All application artifacts live under `src/`:
```
src/
  frontend/         — Next.js application (landing page + Observation Deck)
  backend/          — FastAPI application
    api/            — Route handlers (REST, SSE, WebSocket)
    crew/           — Agent persona definitions (Captain, Navigator, etc.)
    dial_system/    — LLM gateway, provider routing, failover
    execution/      — Sandboxed code execution backends (gVisor/Docker)
    services/       — Business logic layer
    models/         — SQLAlchemy models (including Vivre Card state)
  shared/           — Shared types, schemas, constants
  infra/            — Docker, Kubernetes, Helm configs
```
