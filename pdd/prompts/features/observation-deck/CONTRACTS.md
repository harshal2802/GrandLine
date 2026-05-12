# Observation Deck — Protocol Contracts

Enforceable rules every Phase-16 prompt must respect. Closes the v4–v6 review gaps. Each contract has a **Rule** and **Tests must cover** clause; rationale is one line.

**Cross-reference**: phases in [PLAN-observation-deck.md](PLAN-observation-deck.md) cite contracts by ID (e.g., "(P1)"). New contracts go at the end; never renumber.

---

## P1. WS → SSE fallback after 3 consecutive handshake failures

**Rule**:
- `useVoyageStream` opens WS. Handshake fail = open closes within 5s.
- After 3 fails within 60s → silently swap to SSE (`fetch` + `ReadableStream` against existing `GET /voyages/{id}/stream`).
- Sticky for connection lifetime; manual `reconnect()` retries WS first.
- Store exposes `transport: "ws" | "sse"`. ConnectionState chip surfaces it.
- Beyond SSE failure → `connectionState: "closed"` + manual retry CTA.

**Tests must cover**: 3 WS handshake failures → SSE fallback; SSE message parses identically to WS frame; manual reconnect retries WS first.

**Why**: "transport-agnostic" only matters if fallback actually triggers.

---

## P2. Replay vs live: `liveEpoch` + `replayMode` flag

The SSE/WS replay-from-`id="0"` contract delivers full history on every connect. Side effects must skip historical events.

**Rule**:
- Store has per-voyage `liveEpoch: number` (monotonic). Each new connection: `liveEpoch++`, `replayMode = true`.
- `replayMode → false` on first event with `msg_id > maxKnownMsgId` OR (first connect only) after a 500ms quiet window.
- Every emitted `EventEnvelope` carries `isReplay: boolean` snapshotted at receipt.
- **Side effects (toasts, edge flashes, recent counters, command-palette recents) only fire when `isReplay === false`.** State updates fire either way.

**Tests must cover**: voyage switch resets epoch; reconnect → replay → live transition; toasts/animations skip replayed events; new live events post-replay fire side effects.

**Why**: Reconnect/switch must not re-fire toasts, re-animate edges, or inflate counters.

---

## P3. Canonical event identity

| Field | Source | Used for |
|---|---|---|
| `event_id` | `DenDenMushiEvent.event_id` (UUID, immutable) | Dedupe (the only key) |
| `timestamp` | `DenDenMushiEvent.timestamp` | Display order primary |
| `msg_id` | Redis stream id (monotonic) | Order tie-break + replay/live cutover |
| `CrewActionRead.id` | `crew_actions.id` row PK | Pagination cursor tie-break (P6) |

```ts
type EventEnvelope = {
  event_id: string;     // dedupe
  msg_id: string;       // tie-break + cutover
  ts: number;           // ms; from `timestamp`
  source_role: CrewRole;
  type: EventType;
  payload: Record<string, unknown>;
  isReplay: boolean;    // P2
};
```

**Rule**: Store dedupe = `Map<event_id, EventEnvelope>`. Display sort = `(ts asc, msg_id asc)`. CrewAction merge correlates via backend-written `details.event_id` field.

**Tests must cover**: same `event_id` arriving twice → 1 entry; equal `ts` ordered by `msg_id`; CrewAction REST + WS merge no duplicates.

---

## P4. Auth refresh: 30-min token expiry handled transparently

**Rule**:
- **REST 401** → call `/auth/refresh`, retry once. Refresh fail → clear store + redirect `/login?redirect=<path>`.
- **WS close code 1008** OR close within 5s of open → refresh + reconnect with new token. Refresh fail → close + redirect.
- **Pre-emptive refresh**: when access token's `exp` < 60s away, auth store schedules refresh. JWT exp decoded client-side (no signature check; server still validates).
- `Authorization: Bearer` always reads from store at call time.

**Tests must cover**: 401 → refresh → retry; refresh-token-expired → redirect; pre-emptive refresh fires within 60s of `exp`; WS close-on-auth → reconnect with fresh token.

**Why**: Tokens expire mid-stream on long voyages.

---

## P5. Playback reducer: only milestone-derivable state

The reducer is the only path from raw events to playback state.

```ts
function reducePlayback(events: EventEnvelope[]): PlaybackState {
  // events with ts <= cursorTs reduce into:
  //   status: VoyageStatus            (latest pipeline_stage_entered)
  //   phase_status: Record<int, "PENDING"|"BUILDING"|"BUILT"|"FAILED">
  //   active_crew: CrewRole | null
  //   completed_phases: int[]
  //   failure: { stage, code, message } | null
}
```

**New event types Phase 0 must add to `app/den_den_mushi/events.py`**:

| Event type | Source | Payload | Reducer effect |
|---|---|---|---|
| `phase_build_started` | `ShipwrightService.build_code` start | `{phase_number}` | `phase_status[n] = "BUILDING"` |
| `phase_build_failed` | `ShipwrightService.build_code` failure | `{phase_number, code, message}` | `phase_status[n] = "FAILED"` |
| `tests_passed` (existing) | Shipwright on green | `{phase_number}` | `phase_status[n] = "BUILT"`, push n to completed_phases |
| `pipeline_stage_entered` (existing) | PipelineService | `{stage, voyage_status}` | `status = stage`, `active_crew = source_role` |
| `pipeline_failed` (existing) | PipelineService | `{stage, code, message}` | `failure = {...}` |

**Reconstructible**: `status`, `phase_status`, `active_crew`, `completed_phases`, `failure`, log-up-to-cursor, Crew-Map active node + edge state.

**NOT reconstructible** (don't promise in playback): exact validation result text, past deployment URL, Poneglyph content as it existed at a moment.

**Tests must cover**: stage_entered/completed produce expected `status` per cursor; `phase_build_started → tests_passed` → `BUILDING → BUILT`; `phase_build_started → phase_build_failed` → `BUILDING → FAILED`; rewind before any build → empty `phase_status`.

---

## P6. CrewAction pagination: opaque cursor on `(created_at, id)`

**Rule**:
- Endpoint: `?cursor=<base64>&limit=<int>`. Cursor = `base64url(JSON.stringify({ts, id}))`.
- SQL: `WHERE (created_at, id) < (cursor.ts, cursor.id) ORDER BY created_at DESC, id DESC LIMIT <limit>`.
- Response: `nextCursor: string | null`. First call has no cursor.
- `limit`: default 200, max 1000.
- Frontend treats cursor as opaque.

**Tests must cover**: equal-timestamp rows paginate without dup/skip; `nextCursor === null` at end; invalid cursor → 400.

---

## P7. Voyage list: sort + pagination + freshness

**Rule** for `GET /api/v1/voyages`:
- Default sort `voyage.updated_at DESC, id DESC`.
- Cursor pagination on `(updated_at, id)`. Default limit 50, max 200.
- Optional `?status=active` (excludes COMPLETED/CANCELLED/FAILED) or `?status=terminal`.
- React Query stale time: 30s; refetch on window focus + on WS events that signal voyage transitions.

**Tests must cover**: default sort matches `updated_at DESC`; status filter excludes correctly; cursor pagination stable across equal `updated_at`.

---

## P8. CrewAction action_type taxonomy: locked enum

**Rule**: `app/services/crew_action_helper.py` defines:

```python
class CrewActionType(str, enum.Enum):
    PLAN_CREATED, PONEGLYPH_DRAFTED, HEALTH_CHECK_WRITTEN
    PHASE_BUILD_STARTED, PHASE_BUILD_COMPLETED, PHASE_BUILD_FAILED
    VALIDATION_PASSED, VALIDATION_FAILED
    DEPLOYMENT_STARTED, DEPLOYMENT_COMPLETED, DEPLOYMENT_FAILED
    PIPELINE_PAUSED, PIPELINE_RESUMED, PIPELINE_CANCELLED
    PIPELINE_FAILED, PIPELINE_COMPLETED
```

- `summary`: human-readable ≤ 200 chars.
- `details`: free-form dict with per-type conventions (e.g., `phase_build_completed` has `phase_number, duration_seconds`).
- Frontend Ship's Log groups by `(action_type, phase_number)` for BUILDING actions, by `action_type` otherwise.
- New action_types require both backend constant + frontend grouping entry — no string drift.

**Tests must cover**: backend rejects ad-hoc strings (Pydantic validation); frontend grouping handles every enum value.

---

## P9. Ship's Log live reconciliation

CrewAction is durable; WS publish is best-effort. UI must reconcile on missed publishes.

**Rule** for `useCrewActions`:
- Refetch first page on WS reconnect.
- Refetch on window focus (`refetchOnWindowFocus: true`).
- Periodic poll every 60s while voyage is active. Stops when no voyage selected. Configurable in `lib/preferences.ts` (default 60s; off / 30s / 60s / 120s).
- Poll short-circuited if a WS event arrived in the last 60s.

**Tests must cover**: refetch on WS reconnect; refetch on window focus; periodic poll runs while active and stops on deselect; poll short-circuited when recent WS event seen.

---

## P10. Stream hook respects terminal closure

**Rule**:
- Store subscribes to `useVoyageStatus`. On `status ∈ {COMPLETED, FAILED, CANCELLED}` → `connectionState: "terminal-idle"`. Hook stops reconnect attempts.
- Server signals via WS close code 1000 + reason `"voyage-terminal"` (Phase 0 backend implements).
- Manual reconnect on terminal voyage no-ops with tooltip "voyage is in a terminal state — close and re-open the deck to retry."
- On voyage switch to non-terminal: resumes normal reconnect.
- Distinguished from transient drops on still-running voyages (those retry per P1).

**Tests must cover**: WS closes after voyage flips to COMPLETED → stays in `terminal-idle`, no retry; voyage switch from terminal → active resumes attempts; manual reconnect on terminal no-ops.

---

## P11. Sea Chart pagination: first page + "Show more"

**Rule**:
- Sea Chart fetches first page (`?status=active`) on mount.
- "Show more voyages" button at column-area bottom appends next page (cursor advanced).
- No auto-scroll / auto-load.
- Active voyages render in stage columns; terminal voyages have collapsed Completed/Failed sections with their own "Show more".
- React Query stale time 30s; refetch on focus + on WS voyage-transition events.

**Tests must cover**: first page renders cards in correct columns; "Show more" appends next page; cursor advance is opaque; status filter excludes terminal voyages from active section.

---

## P12. Voyage buffer eviction

**Rule**:
- Store tracks `visitedOrder: string[]` (LRU). On voyage selection: `[active, ...prev.filter(id => id !== active)].slice(0, 3)`.
- Voyages outside LRU (active + 2 most recent) have `events: EventEnvelope[]` cleared. Status snapshots preserved for sidebar rendering.
- Global cap 15k events across all voyages. Exceeded after eviction → drop oldest in the LRU voyage.

**Tests must cover**: switching voyages 4 times keeps event buffers for active + 2 most recent only; sidebar still shows status for all visited; global cap triggers oldest-first within LRU voyage.

---

## P13. Ship's Log canonical timestamp: `crew_action.created_at` everywhere

**Rule**:
- Ship's Log sorts by `crew_action.created_at` (DB) for both REST and WS rows.
- WS `crew_action_recorded` event payload carries `crew_action.created_at` explicitly (Phase 0 backend writes it).
- Tie-break: `crew_action.id` (UUID lex).
- Voyage event store (P3) still orders by `(ts, msg_id)` — that store mixes event types most without a CrewAction.

**Tests must cover**: WS-arrived row interleaves correctly with REST rows by `created_at`; equal-timestamp tie-break by `id`; live merges never visibly reorder rendered rows.

---

## P14. Keyboard shortcut editable-focus guard

**Rule** in `useKeyboardShortcuts`:
- Check `document.activeElement` before firing. Ignore if active element is `INPUT`, `TEXTAREA`, `SELECT`, `[contenteditable=true]`, or `[role="slider"]`.
- Always-honored exceptions: `Esc` (universal blur), palette toggle (`Cmd-K` / `Ctrl-K`).
- Shortcut help dialog (`?`) lists global vs scoped bindings.

**Tests must cover**: `/` in input does NOT trigger search; `[` in scrubber does NOT switch voyage; `Esc` always closes palette; `?` in input does NOT open help.

---

## P15. Independent pagination for Sea Chart and Sidebar

**Rule**:
- `useVoyages` accepts a `queryKey` argument. Sidebar and Sea Chart use distinct keys → distinct caches.
- Both default to first page; both have independent "Show more" controls.
- Cache invalidation triggers (focus, voyage transition events) refresh both.

**Tests must cover**: Sidebar "Show more" doesn't change Sea Chart; Sea Chart "Show more" doesn't affect Sidebar; both invalidate on the same triggers.
