# Implementation Plan: Observation Deck (Phase 16)

**Issue**: #17
**Complexity**: High — broadest plan in the project. Backend retrofit on every crew service + new WS surface, plus a UX-rich frontend with playback, palette, drawer, focus mode, accessibility, and responsive polish.
**Estimated prompts**: 8
**Companion**: [CONTRACTS.md](CONTRACTS.md) — enforceable rules (P1–P15) referenced by every phase.

**Revisions**:
- v1 (2026-04-25): SSE-only, query-param routing, assumed cookie auth, event stream as Ship's Log truth.
- v2 (2026-04-26): adopt WS, route segments, real auth bridge, CrewAction-backed log.
- v3 → withdrawn (frontend-only refocus).
- v4 (2026-04-26): merge v2 backbone + v3 UX.
- v5 (2026-04-26): add P1–P8 contracts (transport fallback, replay/live, canonical id, refresh, reducer, pagination, taxonomy).
- v6 (2026-04-26): add P9–P15 (live reconciliation, terminal closure, paging, eviction, canonical log timestamp, shortcut safety, independent paging).
- v7 (2026-04-27): split contracts into [CONTRACTS.md](CONTRACTS.md); compress decisions and phases; same content, less prose.

## Summary

The Observation Deck is the One Piece-themed war-room dashboard at `/app/*`. Three sibling routes share one live voyage feed:

- **Sea Chart** (`/app/sea-chart`) — Kanban columns for the seven pipeline stages. Rich cards: title, current stage, phase progress bar, last-event-time, failure badge, "Open details" action.
- **Crew Map** (`/app/crew-map`) — animated DAG of the five crew personas. Active node pulses, edges flash on event arrival, transient labels, recent-event counters.
- **Ship's Log** (`/app/ships-log`) — chronological timeline. Loaded from durable `CrewAction` REST (canonical record), live updates via WebSocket, with grouping (by stage / phase / repetitive), client-side filters, and voyage-context search.

All three views share a transport-agnostic event store fed by one WS connection per active voyage. A **details drawer** opens from any view. **Cmd-K command palette** + keyboard shortcuts (`g s`, `g c`, `g l`, `/`, `[`, `]`) cover navigation. **Voyage playback** lets users scrub the event timeline; views render state-as-of-cursor via the P5 reducer. **Focus mode** dims unrelated UI. **Cross-view linking** via shared focus store. **localStorage prefs** persist UI state. **Onboarding cues** appear once per view.

## Scope

### Non-goals
- No new transport beyond REST + SSE + WS.
- No server-side filtering (all client-side).
- No interactive controls (pause/cancel/inject) — Phase 17.
- No multi-voyage concurrent live view — one WS at a time.
- No mobile (desktop-first; tablet supported via fallback).
- No new auth UI flows beyond login/register (no SSO, no email verification, no password reset).
- No persistent playback state across reloads.

### Success criteria
- A new user understands current voyage state within **5 seconds** without reading raw JSON.
- A user traces what happened during a voyage without expanding any technical payload.
- After a stream disconnect, the user recovers without confusion (clear state + manual retry).
- A power user navigates the deck **with keyboard only** (switch voyages/views, search, open details, drive playback).
- Ship's Log is **durable + complete** — backed by `CrewAction` REST, not just the live event stream.

## Locked design decisions

Each is logged in `pdd/context/decisions.md` as part of the relevant phase. Detailed rules → [CONTRACTS.md](CONTRACTS.md).

| # | Decision | Detail | Contracts |
|---|---|---|---|
| 1 | WS as deck live transport; SSE retained for token streaming | New `WS /api/v1/voyages/{id}/events` with `?token=<jwt>` handshake. Existing SSE endpoint stays. Forward-compatible envelope `{type, payload}`. | P1, P10 |
| 2 | Client store transport-agnostic | Normalized `EventEnvelope` shape. Hook hides transport. Connection-state enum identical regardless of transport. | P3 |
| 3 | Routes per convention; voyage in query param | `/app/sea-chart` / `/crew-map` / `/ships-log`; `?voyage=<uuid>`. `/app` redirects to `/sea-chart`. | — |
| 4 | Auth bridge: cookie issuance + bearer + WS query token | Backend `/login` and `/register` set `access_token` cookie (HttpOnly=false for WS handshake) AND return JSON. Frontend uses bearer for REST, cookie token for WS. | P4 |
| 5 | Ship's Log = `CrewAction` REST canonical + WS live updates | Crew services write CrewAction in same transaction as main commit. Frontend merges REST history + WS deltas. | P3, P6, P8, P9, P13 |
| 6 | One deck per voyage; sidebar selector | Voyage selection updates `?voyage=<id>` while keeping view path. One WS connection at a time. | P7, P15 |
| 7 | Voyage playback is local; ring buffer drives it | 5000-event ring buffer; pause/resume/scrub/jump-to-stage/return-to-live. View state derived via P5 reducer. | P5, P12 |
| 8 | Derived progress model; views read selectors | `useVoyageProgress`: percentComplete, phasesBuilt, activeCrewMember, currentStage, failureSummary. Pure fns over store slices. | P5 |
| 9 | Cross-view linking via shared focus store | `useFocus` Zustand store: `hoveredPhase`, `hoveredCrew`, `selectedEventId`. Selection persists; hover doesn't. | — |
| 10 | Tests: vitest + RTL + msw + inline WS mock | Backend gets `test_observation_deck_ws.py` and crew-service test extensions. axe-core smoke from Phase 7. | — |

## Resolved open questions

- **Replayed events trigger UI side effects?** No — P2 locks. Toasts/animations/counters fire only when `isReplay === false`.
- **Playback scope: live buffer only or paginate older?** Live buffer only. Ship's Log paginates older but doesn't extend playback range.
- **Voyage switch during paused playback?** Discard playback state; auto-return to live for the new voyage.
- **CrewAction action_type taxonomy?** Locked enum (P8). Backend rejects ad-hoc strings.

## Phases

### Phase 0: Backend prereqs (CrewAction + WS + cookie + voyages list)

**Produces**:
- `app/services/crew_action_helper.py` with `record_action(...)` + `CrewActionType` enum (P8). Helper writes `details.event_id` for P3 correlation.
- Crew service writes (`captain`, `navigator`, `doctor`, `shipwright`, `helmsman`, `pipeline`) — one CrewAction per meaningful checkpoint, atomic with existing commit.
- New events in `app/den_den_mushi/events.py` (required by P5 reducer): `PhaseBuildStartedEvent`, `PhaseBuildFailedEvent`, `CrewActionRecordedEvent` (latter carries `event_id` + `crew_action_id` + `crew_action.created_at` per P13). All added to `AnyEvent` union.
- `app/api/v1/observation_deck.py`:
  - `GET /voyages` (P7): cursor pagination on `(updated_at, id)`, optional `?status=active|terminal`.
  - `GET /voyages/{id}/crew-actions` (P6): opaque base64 cursor on `(created_at, id)`.
  - `WS /voyages/{id}/events`: `?token=<jwt>` auth, ephemeral consumer group, forwards events. Close 1000 + reason `"voyage-terminal"` on terminal status (P10); close 1008 on expired token (P4).
- `app/api/v1/auth.py` — `/login`, `/register`, `/refresh` set `Set-Cookie: access_token=...; SameSite=Lax; HttpOnly=false; Max-Age=<exp>`.
- `app/schemas/observation_deck.py` — `CrewActionRead` (with `details.event_id`), `VoyageListItem`, cursor models.
- Tests: helper unit (incl. enum rejection); crew-service test extensions per service (~3-5 each); REST list/cursor stability; WS forwarder happy + 1008 + 1000+terminal + 404; auth cookie + refresh.

**Risk**: Medium-High — touches every crew service. Mitigation: small atomic helper + per-service one-liner; TDD; `make test` per edit.

**Prompt**: `grandline-16-00-backend-prereqs.md`

### Phase 1: Frontend foundation

**Produces**:
- Login + register pages (auth API call → cookie set automatically → JSON populates auth store → redirect to `?redirect=` or `/app/sea-chart`).
- `lib/api.ts` — fetch wrapper with bearer-injection + 401 → refresh + retry → fail → redirect (P4). Header reads from store at call time.
- `lib/auth/cookie.ts` (read-only helper); `lib/auth/jwt.ts` (decode `exp` for pre-emptive refresh per P4).
- `stores/auth.ts` — Zustand: `accessToken`, `refreshToken`, `user`, `login()`, `logout()`, `refresh()`. Schedules pre-emptive refresh.
- `stores/voyage.ts` — Zustand with `EventEnvelope` shape (P3); `connectionState` incl. `terminal-idle` (P10); `transport` field (P1); `liveEpoch` + `replayMode` (P2); ring buffer (5000); per-voyage LRU eviction (P12); global 15k cap.
- `hooks/useVoyageStream.ts` — transport-agnostic (P1, P2, P3, P4, P10): WS first; 3 fails in 60s → SSE fallback (sticky); replay→live cutover; refresh+reconnect on auth close; terminal-idle on terminal status; manual `reconnect()` retries WS first.
- `hooks/useVoyages.ts` over `GET /voyages` with status filter + cursor (P7); accepts `queryKey` for P15.
- `hooks/useVoyageStatus.ts` over `GET /voyages/{id}/status`.
- `hooks/useCrewActions.ts` — opaque cursor pagination (P6); reconciliation triggers per P9 (refetch on reconnect / window focus / 60s poll while active, short-circuit on recent WS event).
- `components/observation-deck/`: `ConnectionState.tsx` (state + transport + last-event-ts + manual reconnect; surfaces `terminal-idle`); `Sidebar.tsx` (voyage list, click sets `?voyage=<id>`).
- `app/(app)/layout.tsx` — sidebar + outlet + connection chip; `app/(app)/page.tsx` redirects to `/app/sea-chart`.
- `lib/preferences.ts` — typed `localStorage` wrapper, schema-versioned (`__version: 1`).
- Tests: full P1/P2/P3/P4/P9/P10/P12/P15 coverage per the contracts' "Tests must cover" lines + auth flow + sidebar pagination + ring-buffer cap.

**Risk**: High — most protocol-heavy phase. Mitigation: ship auth → store/envelope → WS hook → SSE fallback → replay/live machinery in that order; tests gate each substep.

**Prompt**: `grandline-16-01-foundation.md`

### Phase 2: Sea Chart — rich cards + derived progress + cross-view hover

**Produces**:
- `app/(app)/sea-chart/page.tsx`.
- `components/observation-deck/SeaChart.tsx` — eight columns (PLANNING → DEPLOYING + COMPLETED + FAILED). First page only on mount; "Show more voyages" button appends next page (P11). Uses own `queryKey` for independent paging (P15). Active voyage updates live; others refresh on focus + transition events.
- `components/observation-deck/SeaChartCard.tsx` — title, current stage, phase progress bar (`phasesBuilt / total`), last-event-time (relative + tooltip absolute), failure badge, "Open details" quick action.
- `hooks/useVoyageProgress.ts` — derived progress selector.
- `stores/focus.ts` — cross-view hover/selection (Decision 9).
- `components/observation-deck/EmptyState.tsx` — "select a voyage" / "voyage has no events yet" / "stream disconnected" shared component.
- Cross-view: hovering a phase number anywhere highlights it in the matching card.
- Tests: cards render + animate on status change; hover updates focus store; empty/loading/error states; progress selector pure-fn; "Show more" advances cursor and appends next page; Sidebar pagination doesn't affect Sea Chart (P15).

**Risk**: Medium.

**Prompt**: `grandline-16-02-sea-chart.md`

### Phase 3: Crew Map — event-reactive DAG

**Produces**:
- `app/(app)/crew-map/page.tsx`.
- `components/observation-deck/CrewMap.tsx` — SVG with five hand-positioned nodes (Captain → Navigator → Doctor → Shipwrights → Doctor → Helmsman), four directed edges.
- Animations (**all gated on `isReplay === false` per P2**):
  - Active node pulses on stage transitions.
  - Edges flash when matching `source_role` event arrives (one short pulse).
  - Transient activity label ("Generating Poneglyphs...") next to active node, fades after 2s.
  - Per-node badge for recent-event count (rolling 60s window of live events only).
- Cross-view: hovering a node updates focus store.
- Tests: nodes render; pulses on stage change; edges flash on event arrival (jest fake timers); transient labels appear/fade; replayed events DO NOT animate; counters do NOT inflate on reconnect.

**Risk**: Medium-High — first complex SVG; cross-browser tuning.

**Prompt**: `grandline-16-03-crew-map.md`

### Phase 4: Ship's Log — grouping, filters, search

**Produces**:
- `app/(app)/ships-log/page.tsx`.
- `components/observation-deck/ShipsLog.tsx` — initial render from `useCrewActions`. Live additions merged from WS `crew_action_recorded` events. **Dedupe by `event_id` (P3); sort by `crew_action.created_at` with `id` tie-break (P13). Reconciliation per P9.** Hand-rolled virtualization (`react-window` only if < 50KB gz).
- Grouping toggles: by stage (default on), by phase (BUILDING events), collapse repetitive (`code_generated` runs).
- Filter chips: crew_role (5), phase number (dynamic), failure-only. State persisted in `localStorage.observation_deck.logFilters` (versioned).
- Voyage-context search across title, event_type, payload text, phase numbers, crew_role.
- Cross-view: row hover updates focus store; rows highlight when phase/crew hovered elsewhere.
- Tests: virtualization with 1000+ events; group toggles; filter chips; search narrows; hover updates focus store; filters persist; WS-arrived row interleaves with REST by `created_at` (P13); equal-`created_at` tie-break by `id` (P13); REST refetch on WS reconnect merges without duplicates (P9).

**Risk**: Medium.

**Prompt**: `grandline-16-04-ships-log.md`

### Phase 5: Details drawer + voyage playback

**Produces**:
- `lib/playback/reducer.ts` — pure `reducePlayback(events) → PlaybackState` (P5). Testable in isolation.
- `components/observation-deck/DetailsDrawer.tsx` — slide-in right drawer; tabs: Overview (plan summary, phase status table from reducer, derived progress), Recent Events (events ≤ cursor, last 50), Timestamps (started, last activity, expected duration). **Tabs only show reducer-contracted state — no past Poneglyph content / past validation text / past deployment URL (P5).**
- `components/observation-deck/PlaybackControls.tsx` — pause/resume; scrubber over `[firstEventTs, lastEventTs]` bounded by ring buffer (resolved open question); jump-to-stage dropdown; "▶ Return to live" when scrubbed back; leftmost-edge marker labeled "earliest event in buffer".
- `stores/playback.ts` — `mode: "live" | "paused" | "scrubbing"`, `cursorTs`, transitions. **On voyage switch: discard state, return to live for new voyage (resolved open question).**
- `useVoyageProgress` + view selectors call `reducePlayback(events.filter(e => e.ts <= cursorTs))` when cursor is set.
- Tests: reducer per-cursor correctness (P5: stage transitions; build_started→tests_passed=BUILT; build_started→build_failed=FAILED; rewind-before-builds=empty); reducer is deterministic + pure; drawer opens from each view trigger and renders all tabs; tabs only show reducer state; playback transitions; views reflect cursor; voyage switch discards state; scrubber bounded by buffer.

**Risk**: High — reducer is load-bearing for everything downstream.

**Prompt**: `grandline-16-05-drawer-playback.md`

### Phase 6: Command palette + shortcuts + focus mode + onboarding + toasts

**Produces**:
- `components/observation-deck/CommandPalette.tsx` — Cmd-K / Ctrl-K opens fuzzy palette: switch view, switch voyage (recent list), jump to stage, open details, toggle focus mode, toggle reduced motion.
- `hooks/useKeyboardShortcuts.ts` — chords: `g s`, `g c`, `g l`, `/`, `[`, `]`, `Esc`, `?`, `f`. **Editable-focus guard per P14** (ignored when focus is in `INPUT`/`TEXTAREA`/`SELECT`/`[contenteditable]`/`[role="slider"]`; `Esc` and palette toggle always honored).
- `components/observation-deck/FocusMode.tsx` — toggle hides sidebar, dims unrelated UI; shows status header + mini Crew Map + log trail. `Esc` exits. Persisted in `localStorage`.
- `components/observation-deck/OnboardingHint.tsx` — dismissible popover per view title on first visit. Persisted as `localStorage.observation_deck.onboarding.{view} = "dismissed"`.
- `components/observation-deck/Toaster.tsx` — custom toast helper (no library unless < 30KB gz). Triggered by store transitions: pipeline started, stage completed, failure detected, deployment completed, stream reconnected. **Only fires on `isReplay === false` (P2).**
- Tests: palette opens/finds/executes; chord shortcuts trigger; focus mode toggles; onboarding hints dismiss + stay dismissed; toasts fire on right transitions; replayed events don't trigger toasts; shortcuts ignored in editable controls (P14); `Esc` and palette toggle always fire.

**Risk**: Medium.

**Prompt**: `grandline-16-06-palette-shortcuts.md`

### Phase 7: Polish — a11y, responsive, motion, perceived perf

**Produces**:
- **Accessibility**: keyboard nav across every interactive element; visible focus rings; ARIA labels on Crew Map nodes/edges, Sea Chart cards, Ship's Log rows; color-independent status indicators (icon + shape); `prefers-reduced-motion: reduce` honored (pulses → fade, no edge flashes, no auto-play); axe-core smoke in CI = 0 violations.
- **Responsive**: desktop-first (≥1280px); tablet (≥768px) sidebar collapses to icon rail; mobile (<768px) explicit "desktop-optimized" banner + read-only Sea Chart card list, Crew Map and playback hidden.
- **Motion + perceived perf**: skeletons for every async surface; optimistic UI for sidebar voyage selection; motion timing tuned (150ms layout / 300ms column moves / 600ms edge flashes — single `transitions.ts`); shared `Card`/`Chip`/`Drawer` primitives; WS event batching at 50ms intervals; memoized selectors.
- Tests: axe smoke per view; reduced-motion variants; responsive breakpoints (RTL viewport mocking); batching test (N events in 50ms = 1 render).

**Risk**: Medium — open-ended; constrain to checklist.

**Prompt**: `grandline-16-07-polish.md`

## Cross-cutting concerns

- **Accessibility**: every interactive surface keyboard-navigable, has visible focus, supports reduced motion, uses color-independent indicators. axe-core CI from Phase 7.
- **Responsive**: desktop-first; tablet supported; mobile graceful read-only fallback. Earlier phases avoid fixed widths.
- **Performance budgets**: deck FMP < 1.5s cold; Sea Chart re-render on event arrival < 16ms; Ship's Log smooth at 1000+ events; WS batching keeps render loops stable.
- **State persistence**: `localStorage` is single source of UI prefs. Schema version field on every key.
- **Test coverage**: stream parsing + reconnect; playback (P5); cross-view sync; keyboard shortcuts (P14); filters + search; drawer; axe smoke.

## Risks & unknowns

- **CrewAction backfill scope creep** — every crew service touched. Mitigation: one row per checkpoint; canonical action_types in constants module (P8).
- **WS reconnection storms** — flaky network spawns ephemeral groups. Bounded but Redis grows. Mitigation: client backoff; server-side orphan-group cleanup older than 1h is a follow-up.
- **Cookie SameSite + cross-origin** — dev (frontend :3000 / backend :8000) is same-site on localhost; prod may differ. CORS already allows dev origin; prod needs same-origin proxy or tighter cookie. Document; revisit before prod.
- **HttpOnly=false cookie** — chosen for WS handshake. XSS exposure documented (Decision 4 + P4); revisit when Phase 17/18 tightens threat model.
- **Phase 0 regression risk on 837 unit + 9 integration tests** — TDD; `make test` per edit.
- **Playback memory pressure** — 5MB × LRU=3 = 15MB. Bounded via P12; drop oldest at boundaries.
- **Cross-view focus performance** — high-frequency hover. Use `useShallow` so unrelated cards don't re-render.
- **Crew Map SVG quirks across browsers** — Phase 3 needs cross-browser smoke.
- **Onboarding fatigue** — cap at one hint per view; never show after dismiss.
- **No `/voyages` endpoint exists today** — Phase 0 adds it; small.

## Next step

Phase 0 is the largest sub-phase but unblocks everything. Open `grandline-16-00-backend-prereqs.md` (write the prompt → spawn an implementation agent) once this plan is approved.
