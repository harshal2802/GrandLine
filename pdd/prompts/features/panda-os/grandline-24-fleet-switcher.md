# Prompt: Fleet Switcher (multi-voyage deck — lossless per-voyage UI state)

**File**: pdd/prompts/features/panda-os/grandline-24-fleet-switcher.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: The voyage event store (`stores/voyage.ts` — `activeVoyageId`, `selectVoyage`, per-voyage `buffers`, LRU `visitedOrder`), the versioned-localStorage helper (`lib/preferences.ts` — `readPref`/`writePref`), the Ship's Log filters (`lib/shipsLog.ts` — `LogFilters`/`EMPTY_FILTERS`/`applyFilters`), the deck shell + sidebar + command palette (`components/observation-deck/{DeckShell,Sidebar,CommandPalette}.tsx`), the voyage list hook (`hooks/useVoyages.ts`)
**Project type**: Frontend (Next.js 14 App Router + React + TypeScript + Tailwind + Zustand + TanStack Query)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. A
competitive review of PandaOS surfaced one last move worth adapting: PandaOS lets
you **switch context without losing terminal/browser/agent state**. GrandLine's
Observation Deck already buffers events per-voyage (`stores/voyage.ts` keeps
per-voyage `buffers`, an LRU `visitedOrder`, and a `selectVoyage(id)` switch
primitive) — but the deck **UI** state is GLOBAL: which view you were on, your
Ship's Log filters, group-by-phase, and scroll position all bleed across voyages
when you switch. A fleet admiral running several concurrent voyages loses their
place every time they hop.

In One Piece the admiral commands a **fleet**, not a single ship — and switching
which ship you're watching shouldn't capsize your view of the others. The **Fleet
Switcher** makes deck UI state **per-voyage and lossless**: each voyage remembers
its own last view, log filters, group-by-phase, and scroll, persisted across
reloads. A quick switcher (consistent with the Command Palette) hops between
concurrent voyages and lands you back exactly where you left that voyage.

The event-buffering store (`voyage.ts`) is NOT duplicated or modified: its
`selectVoyage(id)` stays the single switch primitive (it owns the LRU event ring
and `visitedOrder`); the new deck-state store layers UI state ON TOP, keyed by the
same `voyageId`. The two are siblings — one owns events, one owns view state.

## Task

Implement the Fleet Switcher as a per-voyage deck-state store + a quick switcher
component + wiring into Ship's Log and the deck shell, persisted and SSR-safe:

1. **Per-voyage deck-state store** (`stores/deckState.ts`, Zustand) — keyed by
   `voyageId`. Per-voyage state: `lastView: DeckView` (`"sea-chart" |
   "crew-map" | "ships-log"`), `logFilters: LogFilters` (the exact shape Ship's
   Log uses), `groupByPhase: boolean`, `scroll: Partial<Record<DeckView,
   number>>`. Actions: `setLastView(voyageId, view)`, `setLogFilters(voyageId,
   filters)`, `setGroupByPhase(voyageId, v)`, `setScroll(voyageId, view, top)`,
   and a `getDeckState(voyageId)` selector returning SANE DEFAULTS for an unknown
   voyage (default view `"sea-chart"`, `EMPTY_FILTERS`, `groupByPhase: false`,
   `scroll: {}`). PERSIST the whole keyed map to versioned localStorage by
   REUSING `readPref`/`writePref` with a `DECK_STATE_VERSION`; hydrate once on
   store creation and write on every mutation. Guard against SSR (no `window`/
   `localStorage`) — the helper already no-ops without `localStorage`.

2. **Fleet Switcher component** (`components/observation-deck/FleetSwitcher.tsx`)
   — a quick switcher (modal/overlay, Command-Palette-consistent styling) listing
   voyages from `useVoyages`, each row showing `title` + `StatusBadge`. The
   active voyage is indicated (`aria-current`); ordering puts the voyage store's
   `visitedOrder` recents first, then remaining query order. A type-to-filter
   input narrows by title. Selecting a voyage calls
   `useVoyageStore.getState().selectVoyage(id)` (the switch primitive) AND
   navigates (`useRouter`) to that voyage's restored `lastView`
   (`/app/<lastView>?voyage=<id>`). Keyboard-accessible (Esc closes; the list is
   focusable buttons). Loading / error / empty states required.

3. **Track the active view per voyage** (`hooks/useTrackDeckView.ts`) — a small
   `useTrackDeckView(view: DeckView)` hook each view page calls on mount; it reads
   the active `voyageId` (from the URL) and calls `setLastView(voyageId, view)` so
   the switcher restores the right view. No-op when there's no voyage.

4. **Wire per-voyage state into Ship's Log** (`components/observation-deck/
   ShipsLog.tsx`) — replace the GLOBAL `writePref("logFilters", …)` /
   `useState(groupByPhase)` persistence with the per-voyage deck-state store keyed
   on the active `voyageId`: filters + group-by-phase now come from / write to
   `getDeckState(voyageId)` / `setLogFilters` / `setGroupByPhase`. Restore and
   save the ships-log scroll position via `setScroll`. The single-voyage filtering
   behavior must stay byte-identical (don't regress any current test). Each of the
   three view pages calls `useTrackDeckView(view)`.

5. **Mount the Fleet Switcher** in the deck (`DeckShell.tsx`) and add an open
   trigger + a keyboard shortcut consistent with the existing shortcut surface
   (`lib/shortcuts.ts` + the global handler in `CommandPalette.tsx`). The shortcut
   MUST go through the existing `shouldIgnoreShortcut` editable-focus guard and
   MUST NOT collide with or break the existing shortcuts (`Cmd/Ctrl-K`, the `g`
   chord, `f`, `?`, `/`). Open state lives in the existing `ui` store (a
   `fleetOpen` flag) so it's app-wide and Esc-closable alongside the palette/help.

## Input

- `stores/voyage.ts` — `selectVoyage(id)` (the switch primitive — call it, do not
  reimplement event buffering), `visitedOrder` (LRU recents — read for ordering),
  `activeVoyageId`.
- `stores/ui.ts` — global deck-UI flags pattern (palette/focus/help) to extend
  with `fleetOpen`.
- `lib/preferences.ts` — `readPref`/`writePref` (REUSE for persistence; SSR-safe
  by construction), bump a `DECK_STATE_VERSION`.
- `lib/shipsLog.ts` — `LogFilters`, `EMPTY_FILTERS`, `applyFilters` (the filter
  shape the store stores and Ship's Log consumes).
- `components/observation-deck/{CommandPalette,Sidebar,StatusBadge,EmptyState}.tsx`
  — styling + global-key-handler + voyage-row + status-chip + empty-state patterns
  to mirror.
- `hooks/useVoyages.ts` — the infinite voyage query that populates the switcher.
- Test patterns: `stores/voyage.test.ts` / `stores/auth.test.ts` (Zustand store
  via `getState()`/`setState()`, `beforeEach` reset, `vi` for mocks);
  `lib/voyages.test.ts` (`VoyageListItem`-shaped fixtures). The component test
  mocks `next/navigation` + `useVoyages` with `vi.mock` and renders with React
  Testing Library.

## Output format

- TypeScript/React files following existing conventions: components PascalCase,
  one per file, co-located `*.test.tsx`/`*.test.ts`; explicit `interface` props,
  NO `any`; Tailwind utility classes only; Zustand for app-wide state. One Piece
  terminology ("Fleet Switcher") in names/comments/docs.
- New artifacts under `src/frontend/` (plus this Poneglyph + `pdd/context/` doc
  updates). No backend changes.
- Tests co-located: `stores/deckState.test.ts` (per-voyage isolation, defaults for
  unknown voyage, persistence round-trip with mocked localStorage) and
  `components/observation-deck/FleetSwitcher.test.tsx` (renders voyages, switching
  calls `selectVoyage` + restores the view, empty/loading states).

## Constraints

- Drive every switch through `useVoyageStore.selectVoyage(id)` — the deck-state
  store NEVER re-implements event buffering or the LRU; it layers UI state on the
  same `voyageId` key.
- Per-voyage keying (a `Record<voyageId, DeckUiState>`), not a global blob — that
  is the whole point (lossless, no bleed). Defaults are returned for any unknown
  voyage so a never-seen voyage reads cleanly.
- Persistence REUSES `readPref`/`writePref` with a dedicated `DECK_STATE_VERSION`;
  a version bump falls back to defaults (the helper guarantees this), never throws
  on stale data.
- ALL `window`/`localStorage` access is SSR-guarded (the helper no-ops without
  `localStorage`; the store hydrates lazily/guarded).
- The keyboard shortcut goes through `shouldIgnoreShortcut` and does not break any
  existing shortcut or the palette/help/focus toggles.
- Loading, error, and empty states for every async surface (the switcher list).
- Do NOT regress existing tests; ADD new ones. Single-voyage Ship's Log behavior
  stays identical.

## Edge Cases

- Unknown / never-visited voyage -> `getDeckState` returns sane defaults
  (`sea-chart`, `EMPTY_FILTERS`, no group, empty scroll); nothing throws.
- Setting voyage A's filters/group/scroll NEVER affects voyage B (per-voyage
  isolation is the core invariant).
- SSR / no `window` -> hydration and writes no-op via the `localStorage`-undefined
  guard; defaults are used.
- Stale persisted shape (version mismatch) -> falls back to an empty map, deck
  reads defaults — no crash.
- No active voyage (`voyageId === null`) -> Ship's Log keeps its "Select a voyage"
  empty state; `useTrackDeckView` no-ops; the switcher still lists voyages and
  selecting one sets it active.
- Empty fleet (no voyages) -> switcher shows an empty state, not a blank modal.
- Switching to a voyage restores its `lastView`; a voyage never visited lands on
  the default `sea-chart`.
- The shortcut fired while typing in a search/input is ignored (editable-focus
  guard), exactly like the other single-key shortcuts.
