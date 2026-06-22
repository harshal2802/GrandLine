// Per-voyage deck UI state (Zustand) — Phase 24 "Fleet Switcher".
//
// The voyage event store (`stores/voyage.ts`) owns per-voyage EVENT buffers + the
// LRU `visitedOrder`, and `selectVoyage(id)` is the single switch primitive. This
// store is its sibling: it owns the per-voyage UI/view state — last view, Ship's
// Log filters, group-by-phase, and scroll — keyed by the SAME `voyageId`, so a
// fleet admiral hops between concurrent voyages losslessly. Deck UI state used to
// be GLOBAL and bled across voyages on switch; keying it per-voyage fixes that.
//
// Persisted to versioned localStorage by reusing `readPref`/`writePref` so state
// survives reloads (lossless). SSR-safe: the preference helper no-ops without a
// `localStorage`.

import { create } from "zustand";
import { readPref, writePref } from "@/lib/preferences";
import { EMPTY_FILTERS, type LogFilters } from "@/lib/shipsLog";

export type DeckView = "sea-chart" | "crew-map" | "ships-log";

export interface DeckUiState {
  lastView: DeckView;
  logFilters: LogFilters;
  groupByPhase: boolean;
  scroll: Partial<Record<DeckView, number>>;
}

// Bump when the persisted shape changes — a mismatch falls back to defaults
// (the preference helper guarantees this; stale data never throws).
export const DECK_STATE_VERSION = 1;
const DECK_STATE_KEY = "deckState";

export function defaultDeckState(): DeckUiState {
  return {
    lastView: "sea-chart",
    logFilters: EMPTY_FILTERS,
    groupByPhase: false,
    scroll: {},
  };
}

type DeckStateMap = Record<string, DeckUiState>;

interface DeckStateStore {
  byVoyage: DeckStateMap;
  setLastView: (voyageId: string, view: DeckView) => void;
  setLogFilters: (voyageId: string, filters: LogFilters) => void;
  setGroupByPhase: (voyageId: string, value: boolean) => void;
  setScroll: (voyageId: string, view: DeckView, top: number) => void;
  getDeckState: (voyageId: string) => DeckUiState;
  reset: () => void;
}

function hydrate(): DeckStateMap {
  // SSR-safe via the preference helper (no-ops without `localStorage`).
  return readPref<DeckStateMap>(DECK_STATE_KEY, DECK_STATE_VERSION, {});
}

function persist(byVoyage: DeckStateMap): void {
  writePref(DECK_STATE_KEY, DECK_STATE_VERSION, byVoyage);
}

// Read-or-default for a voyage without mutating the map.
function entry(byVoyage: DeckStateMap, voyageId: string): DeckUiState {
  return byVoyage[voyageId] ?? defaultDeckState();
}

export const useDeckStateStore = create<DeckStateStore>((set, get) => ({
  byVoyage: hydrate(),

  setLastView: (voyageId, lastView) =>
    set((state) => {
      const byVoyage = {
        ...state.byVoyage,
        [voyageId]: { ...entry(state.byVoyage, voyageId), lastView },
      };
      persist(byVoyage);
      return { byVoyage };
    }),

  setLogFilters: (voyageId, logFilters) =>
    set((state) => {
      const byVoyage = {
        ...state.byVoyage,
        [voyageId]: { ...entry(state.byVoyage, voyageId), logFilters },
      };
      persist(byVoyage);
      return { byVoyage };
    }),

  setGroupByPhase: (voyageId, groupByPhase) =>
    set((state) => {
      const byVoyage = {
        ...state.byVoyage,
        [voyageId]: { ...entry(state.byVoyage, voyageId), groupByPhase },
      };
      persist(byVoyage);
      return { byVoyage };
    }),

  setScroll: (voyageId, view, top) =>
    set((state) => {
      const current = entry(state.byVoyage, voyageId);
      const byVoyage = {
        ...state.byVoyage,
        [voyageId]: { ...current, scroll: { ...current.scroll, [view]: top } },
      };
      persist(byVoyage);
      return { byVoyage };
    }),

  getDeckState: (voyageId) => entry(get().byVoyage, voyageId),

  reset: () => {
    persist({});
    set({ byVoyage: {} });
  },
}));
