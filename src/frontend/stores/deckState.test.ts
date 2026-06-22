import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  DECK_STATE_VERSION,
  defaultDeckState,
  useDeckStateStore,
} from "@/stores/deckState";
import { EMPTY_FILTERS, type LogFilters } from "@/lib/shipsLog";
import { readPref } from "@/lib/preferences";

const STORAGE_KEY = "observation_deck.deckState";

beforeEach(() => {
  localStorage.clear();
  useDeckStateStore.getState().reset();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("defaults for an unknown voyage", () => {
  it("returns sane defaults without mutating the map", () => {
    const s = useDeckStateStore.getState();
    expect(s.getDeckState("never-seen")).toEqual(defaultDeckState());
    expect(s.getDeckState("never-seen").lastView).toBe("sea-chart");
    expect(s.getDeckState("never-seen").logFilters).toBe(EMPTY_FILTERS);
    expect(s.getDeckState("never-seen").groupByPhase).toBe(false);
    expect(s.getDeckState("never-seen").scroll).toEqual({});
    // Reading defaults must not persist an entry.
    expect(useDeckStateStore.getState().byVoyage["never-seen"]).toBeUndefined();
  });
});

describe("per-voyage isolation", () => {
  it("setting voyage A never affects voyage B", () => {
    const s = useDeckStateStore.getState();
    const filtersA: LogFilters = { ...EMPTY_FILTERS, search: "captain", failureOnly: true };

    s.setLastView("A", "ships-log");
    s.setLogFilters("A", filtersA);
    s.setGroupByPhase("A", true);
    s.setScroll("A", "ships-log", 420);

    const a = useDeckStateStore.getState().getDeckState("A");
    expect(a.lastView).toBe("ships-log");
    expect(a.logFilters.search).toBe("captain");
    expect(a.groupByPhase).toBe(true);
    expect(a.scroll["ships-log"]).toBe(420);

    // B is untouched — still pure defaults.
    expect(useDeckStateStore.getState().getDeckState("B")).toEqual(defaultDeckState());
  });

  it("scroll is tracked independently per view", () => {
    const s = useDeckStateStore.getState();
    s.setScroll("A", "ships-log", 100);
    s.setScroll("A", "crew-map", 250);
    const a = useDeckStateStore.getState().getDeckState("A");
    expect(a.scroll["ships-log"]).toBe(100);
    expect(a.scroll["crew-map"]).toBe(250);
    expect(a.scroll["sea-chart"]).toBeUndefined();
  });
});

describe("persistence round-trip (versioned localStorage)", () => {
  it("writes a versioned blob that survives reload", () => {
    useDeckStateStore.getState().setLastView("A", "crew-map");
    useDeckStateStore.getState().setGroupByPhase("A", true);

    const raw = localStorage.getItem(STORAGE_KEY);
    expect(raw).not.toBeNull();
    const parsed = JSON.parse(raw as string);
    expect(parsed.__version).toBe(DECK_STATE_VERSION);
    expect(parsed.A.lastView).toBe("crew-map");
    expect(parsed.A.groupByPhase).toBe(true);
  });

  it("ignores a stale persisted version and falls back to defaults", () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ A: { lastView: "ships-log" }, __version: DECK_STATE_VERSION + 99 }),
    );
    // getDeckState reads in-memory state; the fallback happens at hydrate time, so
    // assert via the helper contract: a mismatched version yields no entry.
    const hydrated = readPref("deckState", DECK_STATE_VERSION, {});
    expect(hydrated).toEqual({});
  });
});
