# Prompt: Changes View (artifact-based code browser — Phase A1)

**File**: pdd/prompts/features/deck-capabilities/deck-cap-01-changes-view.md
**Created**: 2026-06-22
**Updated**: 2026-06-22
**Depends on**: The build-artifacts backend (already shipped: `BuildArtifact{file_path, content, language, phase_number}` stored by the Shipwright and served by `GET /api/v1/voyages/{voyage_id}/build-artifacts` → `BuildArtifactListResponse`), the REST fetch wrapper + React Query hook pattern (`lib/api.ts` `apiFetch`, `hooks/useVoyages.ts` / `hooks/useCrewActions.ts`), the Details drawer host (`components/observation-deck/DetailsDrawer.tsx`) and its panel precedent (`components/observation-deck/DialPanel.tsx`), the shared domain types (`lib/types.ts`)
**Project type**: Frontend (Next.js 14 App Router + React + TypeScript + Tailwind + Zustand + TanStack Query)

## Context

GrandLine is a One Piece-themed multi-agent software-orchestration platform. Users
watch the crew voyage through the pipeline on the Observation Deck — but they
can't yet *see the code the crew produced*. The Shipwright already persists every
generated file as a `BuildArtifact{file_path, content, language, phase_number}`
and the backend already serves them (`GET /voyages/{id}/build-artifacts`, optional
`?phase_number=`). Nothing on the deck surfaces them.

This is the first slice of the Code Review workstream (PLAN-deck-capabilities.md,
Phase A1). It is deliberately the **always-available, no-git, no-Cabin** view: it
reads the stored artifacts directly, so it works for every voyage regardless of
whether it used git. Real git diffs (A2) and per-user GitHub (A3) are later phases
that build on the Cabin/Sea Chest foundation; A1 needs none of that and can ship
immediately.

## Task

Add a **"Changes" tab** to the Details drawer that lists the crew's built files,
grouped by phase, with the selected file's content syntax-highlighted:

1. **Type** (`lib/types.ts`) — a `BuildArtifact` type mirroring the backend
   `BuildArtifactRead`, snake_case as the API returns it: `{id, voyage_id,
   shipwright_run_id, phase_number, file_path, content, language, created_by,
   created_at}`.

2. **Hook** (`hooks/useBuildArtifacts.ts`) — a React Query `useQuery` over
   `apiFetch<{artifacts: BuildArtifact[]}>('/voyages/${voyageId}/build-artifacts')`.
   OMIT `phase_number` so it returns artifacts for ALL phases in one read (the
   component groups client-side). `enabled` only when a `voyageId` is present.
   Co-located test (`useBuildArtifacts.test.ts`): mocks `apiFetch`, asserts the
   URL and the returned artifacts, and that it stays idle with no voyage.

3. **Component** (`components/observation-deck/ChangesPanel.tsx`,
   `interface ChangesPanelProps { voyageId: string | null }`) — fetch via the
   hook. Render a list of files **grouped by phase** ("Phase 1" → `src/main.py`,
   …) and a pane showing the selected file's **syntax-highlighted** `content` with
   its `file_path` header and a `language` badge. Selected file is local
   `useState` (A1). **Loading / error / empty** states required (empty = "No
   changes yet — the crew hasn't built any files."). Tailwind only, matching the
   deck's nautical dark theme (mirror `DialPanel`). Co-located test
   (`ChangesPanel.test.tsx`): groups by phase, selecting a file shows its content
   + language badge, and the loading/error/empty states.

4. **Syntax highlighting** — add the lightweight `prism-react-renderer` dependency
   (small, React-native, no global CSS import) and use it in `ChangesPanel` with a
   dark theme (`themes.oceanicNext`). Normalize common `language` strings to Prism
   grammars and fall back to plain text on an unknown grammar so it never throws.

5. **Drawer wiring** (`components/observation-deck/DetailsDrawer.tsx`) — add
   `"changes"` to the `Tab` union and the tabs array, and a render branch
   `{tab === "changes" && <ChangesPanel voyageId={drawerVoyageId} />}`. Existing
   tabs keep working.

## Input

- Backend contract (do NOT change): `GET /api/v1/voyages/{voyage_id}/build-artifacts`
  (optional `?phase_number=`; OMIT for all phases) → `BuildArtifactListResponse
  {voyage_id, phase_number, artifacts: BuildArtifactRead[]}`. See
  `src/backend/app/schemas/build_artifact.py`, `src/backend/app/api/v1/shipwright.py`.
- `lib/api.ts` — `apiFetch<T>` (token injection, 401 refresh-retry).
- `hooks/useVoyages.ts`, `hooks/useCrewActions.ts` — React Query + `apiFetch`
  hook pattern (query key, `enabled` gating).
- `components/observation-deck/DialPanel.tsx` — drawer-panel precedent
  (loading/error/empty handling, nautical dark `ocean-*` Tailwind palette).
- `components/observation-deck/DetailsDrawer.tsx` — the host (`Tab` union, tabs
  array, render branches).
- Test patterns: `hooks/useVoyageProgress.test.ts`,
  `components/observation-deck/FleetSwitcher.test.tsx` (`vi.mock` the hook /
  `apiFetch`, RTL render, controllable mock result object).

## Output format

- TypeScript/React files following existing conventions: components PascalCase,
  one per file, co-located `*.test.tsx`/`*.test.ts`; explicit `interface` props,
  NO `any`; Tailwind utility classes only; React Query for the fetch. One Piece
  themed, friendly copy.
- New artifacts under `src/frontend/` (plus this Poneglyph + `pdd/context/` doc
  updates). No backend changes.

## Constraints

- React Query for the fetch — no manual `fetch` in the component.
- The hook OMITS `phase_number` (all phases in one read); the component groups by
  phase client-side.
- Loading, error, and empty states for the async surface.
- TypeScript strict, explicit `interface` props, NO `any`, Tailwind only.
- Add ONLY a lightweight highlighter (`prism-react-renderer`) — no global CSS
  import, no heavy/global-side-effect dependency.
- Do NOT touch the backend; do NOT regress existing tests — ADD new ones.

## Edge Cases

- No `voyageId` (`null`) → the hook is disabled (idle), nothing fetches.
- Voyage with no artifacts → empty state ("No changes yet — the crew hasn't built
  any files."), not a blank pane.
- Unknown / unmapped `language` → falls back to plain-text highlighting, never
  throws on a missing Prism grammar.
- Multiple phases → files grouped under ascending "Phase N" headers; files sorted
  by path within a phase.
- Fetch error → error state, not a crash or a blank pane.
- Selecting a file shows that file's content + `file_path` header + `language`
  badge; the first file is shown by default before any selection.
