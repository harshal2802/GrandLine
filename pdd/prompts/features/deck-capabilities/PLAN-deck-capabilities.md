# Implementation Plan: Observation Deck Capabilities

**Created**: 2026-06-22
**Updated**: 2026-06-22 (scope locked from decisions)
**Complexity**: High — a security-sensitive epic unified by a per-user container foundation
**Status**: PLAN — decisions locked; ready to decompose into Poneglyphs

## Summary

Three user-facing capabilities the Observation Deck lacks today:
- **A. Code Review** — view the crew's changes (file/diff browser) **+ per-user GitHub**.
- **B. Live App** — run the built app, see it, stream logs, **+ interactive terminal**.
- **C. Dial Config** — configure Claude Code from the UI, **with per-user credentials**.

**Locked decisions (2026-06-22):**
1. Code review depth → **A1 + A2 + A3** (artifacts view → real git diffs → per-user GitHub OAuth).
2. Live app scope → **B0–B3** (real preview backend → logs → embedded preview → interactive PTY terminal).
3. Preview infra → **subprocess inside the gVisor sandbox** (reuse our isolation; no external platform).
4. Dial config → **maintain each user's Claude Code credentials in a separate per-user container**.

Decision (4) is the keystone: it turns "per-user credentials" into a shared backbone. A3
(GitHub token), C (Claude Code login), B0/B3 (running the app + shelling into it) all need the
*same* thing — **a persistent, per-user, isolated container that safely holds the user's
secrets and runs their workloads**. We build that once, first.

## The keystone foundation: the **Cabin** (per-user sandbox) + **Sea Chest** (credential vault)

### Phase 0: Cabin + Sea Chest
**Produces**: A persistent, per-user gVisor container (the **Cabin**) and an encrypted
per-user credential vault (the **Sea Chest**) injected into it. Nothing user-facing yet — this
is the secure substrate A3/B/C all build on.
**Backend**:
- **Cabin lifecycle**: extend the Execution layer from one-shot to a *persistent, per-user*
  container with: gVisor (`runsc`), **network egress allow-list** (deny by default; only the
  hosts a phase needs — e.g. `api.github.com`, the Anthropic endpoint, package registries),
  CPU/mem quotas, **hard max lifetime + idle reaper**, orphan cleanup, and one Cabin per user
  (not per voyage). New `CabinService` + `CabinBackend` (mirrors `ExecutionBackend`/
  `DeploymentBackend` swap pattern).
- **Sea Chest**: per-user secret storage encrypted at rest (envelope encryption; key from env/
  KMS, never the secrets themselves in plaintext in DB). Secrets are **materialized only inside
  the user's Cabin** (e.g. mounted as files / env at process spawn), never returned to the
  browser or logged. Stores: Claude Code session/token (C), GitHub token (A3). New
  `SeaChestService` + a `UserCredential` model (ciphertext + metadata only).
**Security (this is the crown-jewel phase — gets its own security review):** encryption at
rest, no plaintext egress, container isolation between users, least-privilege network, audit
log of credential use, secret rotation/revocation, and reaping so a Cabin can't outlive its
need.
**Risk**: **Highest** (new credential surface + long-lived containers). **Size**: L.
**Everything below depends on Phase 0.**

## Shared sub-foundations (built alongside Phase 0, reused widely)
1. **Bidirectional WS** — generalize the deck WS to accept upstream frames
   (`{"type": "...", "payload": {...}}`); needed by B3 terminal input. (Phase 17 reserved this.)
2. **Drawer-tab / deck-view extension pattern** — A & C mount as Details-drawer tabs; B mounts
   as a top-level deck view. Establish once.
3. **Per-voyage / per-user client buffers** — reuse the Fleet Switcher `deckState` store for
   lossless per-voyage diffs/logs/terminal scrollback.
4. **Default-deny owner-scoping** (`get_authorized_voyage` / per-user) on every new endpoint.

---

## Workstream A — Code Review (A1 → A2 → A3, full)

- **A1 — Artifacts "Changes" view** *(no git, no Cabin)*: a Details-drawer tab rendering
  `BuildArtifact{file_path, content}` (already stored + served) as a per-phase file tree with
  syntax highlighting (`shiki`/`prismjs`). Always-available fallback. **Size S–M.**
- **A2 — Real git diffs**: new `GitService.diff / list_changed_files / get_file_content` +
  `GET /voyages/{id}/git/diff|changed-files|file-content` (owner-scoped) + a unified/split diff
  viewer (`react-diff-viewer-continued`). Falls back to A1 when the voyage didn't use git.
  **Depends on A1. Size M.**
- **A3 — Per-user GitHub** *(depends on Phase 0)*: GitHub OAuth (App/device flow) → token in the
  **Sea Chest** → `GitService` clones/commits/PRs run in the user's **Cabin** with *their* token
  and identity; the deck links to the real PR; connection status UI. Replaces the single env
  token for user-initiated git. **Depends on Phase 0. Size L.**

## Workstream B — Live App (B0 → B1 → B2 → B3, full; subprocess in the Cabin)

- **B0 — Real preview backend** *(depends on Phase 0)*: launch the crew's app as a *long-running
  subprocess inside the user's Cabin* (e.g. `npm start` / `uvicorn …`), capture a real
  reachable URL, tee stdout/stderr to a log sink. Extend the Cabin contract with
  `start_service / logs / stop`. Replaces the synthetic-URL stub in `InProcessDeploymentBackend`.
  Network: localhost + allow-listed only; hard lifetime cap. **Linchpin of B. Size L.**
- **B1 — Log streaming**: tail the B0 sink → `AppLogChunkEvent` over Den Den Mushi → WS (or a
  dedicated SSE), rendered in a Logs panel (virtualized, follow/pause/filter). **Depends B0. Size M.**
- **B2 — Embedded preview**: iframe the B0 URL in a new deck view (sandboxed iframe; CSP
  `frame-src` wiring), with restart/health. **Depends B0. Size M.**
- **B3 — Interactive terminal**: PTY in the Cabin (`tty=True`, attach), inbound WS frames
  (`terminal_input` + resize) on the bidirectional-WS foundation, `xterm.js` UI. Largest attack
  surface → **dedicated security review**. **Depends B0 + bidirectional WS. Size L.**

## Workstream C — Dial Config with per-user Claude Code credentials (C0 → C1 → C2)

- **C0 — Per-user Claude Code credentials in the Cabin** *(depends on Phase 0)*: a UI flow to
  connect Claude Code per user — either paste a `CLAUDE_CODE_OAUTH_TOKEN` or run the
  `claude` device-code/`login` flow — stored in the **Sea Chest**. The `claude_code` adapter is
  reworked to **exec the CLI inside the requesting user's Cabin** with *their* credentials,
  replacing today's host-level, single-credential execution. Connection status surfaced in the UI.
  **Depends on Phase 0. Size L.**
- **C1 — Per-role claude_code options**: mirror `ShipwrightRoleConfig.max_concurrency` —
  `ClaudeCodeRoleConfig{max_turns,…}` carried in `role_mapping[role]`, resolved by the factory,
  safe knobs only (`cli_path`/`workspace`/`extra_args` stay host-level). **Size S.**
- **C2 — DialPanel UI**: claude_code connection status + per-role options + editable fallback
  chains (read-only today). **Depends C1. Size M.**

---

## Dependency graph & sequencing

```
Phase 0 (Cabin + Sea Chest)  ── the keystone; everything secret/runtime depends on it
   ├─ A3 (per-user GitHub)
   ├─ B0 → B1, B2, B3*           (* B3 also needs bidirectional WS)
   └─ C0 (per-user Claude Code)
A1 → A2                         (independent of Phase 0; can start immediately)
C1 → C2                         (C1 independent; C2 surfaces C0 + C1)
bidirectional WS                (sub-foundation; gates B3)
```

**Recommended order:**
1. **A1** + **C1** — quick, independent wins that need no new infra (warm-up, immediate value).
2. **Phase 0 (Cabin + Sea Chest)** — the secure substrate. Security review here.
3. **C0** + **A3** — light up per-user Claude Code and per-user GitHub on the substrate.
4. **A2** + **C2** — diff viewer and the full Dial UI.
5. **B0 → B1 → B2** — real preview + logs + embed.
6. **bidirectional WS → B3** — interactive terminal, behind its own security review.

Each phase = one Poneglyph = one stacked PR, TDD-first, docs + `decisions.md` in the same change.

## Risks & cross-cutting concerns
- **Phase 0 is the make-or-break security phase** — per-user secret storage + long-lived,
  network-capable containers. Mishandling leaks credentials or enables escape. Dedicated review,
  envelope encryption, least-privilege egress, reaping, audit.
- **B3 interactive shell** and **C0 running a CLI with the user's live token** are powerful and
  dangerous; both ride on Phase 0's isolation and each gets a security gate.
- **claude_code rework (C0)** changes the adapter's execution model (host → per-user Cabin) —
  touches the Dial router/factory; keep other providers untouched.
- **Multi-worker**: Cabins, preview processes, and the WS registry are process-local (v1
  single-worker); horizontal scale needs Redis-backed lifecycle (note, don't solve now).
- **Cost/resource**: one persistent Cabin per active user — quotas + idle reaping are mandatory.
- **CSP**: B2 iframe + new origins need `next.config.mjs` updates.

## Decisions — resolved
- Scope A=A1+A2+A3, B=B0–B3, preview=subprocess-in-gVisor, C=per-user creds in a per-user
  container — all **locked** (2026-06-22). Open sub-questions deferred to each phase's Poneglyph
  (e.g. GitHub App vs OAuth-token flow; device-code vs token-paste for Claude Code; KMS vs
  env-key for Sea Chest encryption).
