"use client";

import { useCallback, useMemo, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { useCrewActions } from "@/hooks/useCrewActions";
import { useActiveVoyageEvents } from "@/hooks/useActiveVoyageEvents";
import { useFocusStore } from "@/stores/focus";
import { useDeckStateStore } from "@/stores/deckState";
import { useTrackDeckView } from "@/hooks/useTrackDeckView";
import {
  applyFilters,
  EMPTY_FILTERS,
  mergeLog,
  rowFromCrewAction,
  rowFromEvent,
  type LogFilters,
  type LogRow,
} from "@/lib/shipsLog";
import { CREW_ROLES } from "@/lib/types";
import { EmptyState } from "./EmptyState";

const MAX_RENDER = 500; // soft virtualization cap

export function ShipsLog() {
  const params = useSearchParams();
  const voyageId = params.get("voyage");

  useTrackDeckView("ships-log");

  const { data, isLoading, error, fetchNextPage, hasNextPage } = useCrewActions({ voyageId });
  const events = useActiveVoyageEvents();

  const setHoveredPhase = useFocusStore((s) => s.setHoveredPhase);
  const hoveredPhase = useFocusStore((s) => s.hoveredPhase);
  const hoveredCrew = useFocusStore((s) => s.hoveredCrew);

  // Per-voyage deck state (Phase 24): filters + group-by-phase + scroll are kept
  // per voyage and persisted, so switching voyages is lossless. Subscribe to the
  // active voyage's persisted slice so a switch re-reads the right state.
  const deck = useDeckStateStore((s) =>
    voyageId ? s.byVoyage[voyageId] : undefined,
  );
  const filters = deck?.logFilters ?? EMPTY_FILTERS;
  const groupByPhase = deck?.groupByPhase ?? false;

  const setFilters = useCallback(
    (next: LogFilters | ((f: LogFilters) => LogFilters)) => {
      if (!voyageId) return;
      const current = useDeckStateStore.getState().getDeckState(voyageId).logFilters;
      const resolved = typeof next === "function" ? next(current) : next;
      useDeckStateStore.getState().setLogFilters(voyageId, resolved);
    },
    [voyageId],
  );

  const setGroupByPhase = useCallback(
    (next: boolean | ((g: boolean) => boolean)) => {
      if (!voyageId) return;
      const current = useDeckStateStore.getState().getDeckState(voyageId).groupByPhase;
      const resolved = typeof next === "function" ? next(current) : next;
      useDeckStateStore.getState().setGroupByPhase(voyageId, resolved);
    },
    [voyageId],
  );

  // Restore + persist the ships-log scroll position per voyage.
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const restoreScroll = useCallback(
    (el: HTMLDivElement | null) => {
      scrollRef.current = el;
      if (el && voyageId) {
        const top = useDeckStateStore.getState().getDeckState(voyageId).scroll["ships-log"];
        if (typeof top === "number") el.scrollTop = top;
      }
    },
    [voyageId],
  );
  const onScroll = useCallback(() => {
    if (voyageId && scrollRef.current) {
      useDeckStateStore.getState().setScroll(voyageId, "ships-log", scrollRef.current.scrollTop);
    }
  }, [voyageId]);

  const rows = useMemo(() => {
    const restRows = (data?.pages.flatMap((p) => p.items) ?? []).map(rowFromCrewAction);
    const liveRows = events
      .map(rowFromEvent)
      .filter((r): r is LogRow => r !== null);
    return mergeLog(restRows, liveRows);
  }, [data, events]);

  const filtered = useMemo(() => applyFilters(rows, filters), [rows, filters]);

  const toggleRole = (role: string) =>
    setFilters((f) => ({
      ...f,
      crewRoles: f.crewRoles.includes(role)
        ? f.crewRoles.filter((r) => r !== role)
        : [...f.crewRoles, role],
    }));

  if (!voyageId) {
    return <EmptyState title="Select a voyage" hint="The Ship's Log records every crew action." icon="📜" />;
  }
  if (isLoading) return <EmptyState title="Reading the log…" icon="📜" />;
  if (error) return <EmptyState title="Couldn't load the log" icon="⚠️" />;

  return (
    <div className="flex h-full flex-col gap-3">
      {/* Filters */}
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <input
          type="search"
          placeholder="Search the log…"
          value={filters.search}
          onChange={(e) => setFilters((f) => ({ ...f, search: e.target.value }))}
          className="rounded-md border border-ocean-700 bg-ocean-950 px-3 py-1.5 text-ocean-100 outline-none focus:border-ocean-400"
        />
        {CREW_ROLES.map((r) => (
          <button
            key={r}
            onClick={() => toggleRole(r)}
            className={`rounded-full px-2 py-1 ${
              filters.crewRoles.includes(r)
                ? "bg-ocean-600 text-ocean-50"
                : "bg-ocean-900 text-ocean-400 hover:bg-ocean-800"
            }`}
          >
            {r}
          </button>
        ))}
        <button
          onClick={() => setFilters((f) => ({ ...f, failureOnly: !f.failureOnly }))}
          className={`rounded-full px-2 py-1 ${
            filters.failureOnly ? "bg-rose-500/30 text-rose-200" : "bg-ocean-900 text-ocean-400 hover:bg-ocean-800"
          }`}
        >
          failures only
        </button>
        <button
          onClick={() => setGroupByPhase((g) => !g)}
          className={`rounded-full px-2 py-1 ${
            groupByPhase ? "bg-ocean-600 text-ocean-50" : "bg-ocean-900 text-ocean-400 hover:bg-ocean-800"
          }`}
        >
          group by phase
        </button>
        {filters !== EMPTY_FILTERS && (
          <button onClick={() => setFilters(EMPTY_FILTERS)} className="text-ocean-500 underline">
            clear
          </button>
        )}
      </div>

      {/* Log */}
      <div
        ref={restoreScroll}
        onScroll={onScroll}
        className="flex-1 overflow-auto rounded-lg border border-ocean-800 bg-ocean-900/30"
      >
        {filtered.length === 0 ? (
          <EmptyState title="No matching entries" hint="Adjust filters or wait for the crew to act." />
        ) : (
          <ul className="divide-y divide-ocean-800/60">
            {filtered.slice(0, MAX_RENDER).map((row) => {
              const failure = /fail/i.test(row.actionType);
              const switched = row.actionType === "provider_switched";
              const highlighted =
                (hoveredPhase !== null && row.phaseNumber === hoveredPhase) ||
                (hoveredCrew !== null && row.crewMember === hoveredCrew);
              return (
                <li
                  key={row.event_id}
                  onMouseEnter={() => row.phaseNumber !== null && setHoveredPhase(row.phaseNumber)}
                  onMouseLeave={() => setHoveredPhase(null)}
                  className={`flex items-start gap-3 px-4 py-2.5 text-sm transition-colors ${
                    highlighted ? "bg-ocean-800/50" : ""
                  }`}
                >
                  <span className="w-16 shrink-0 text-[11px] text-ocean-500">
                    {new Date(row.createdAt).toLocaleTimeString()}
                  </span>
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-medium ${
                      failure
                        ? "bg-rose-500/20 text-rose-300"
                        : switched
                          ? "bg-amber-500/20 text-amber-300"
                          : "bg-ocean-800 text-ocean-300"
                    }`}
                  >
                    {row.crewMember}
                  </span>
                  <div className="min-w-0 flex-1">
                    <p
                      className={`truncate ${switched ? "text-amber-200" : "text-ocean-100"}`}
                    >
                      {switched && "⚡ "}
                      {row.summary}
                    </p>
                    <p className="text-[11px] text-ocean-500">
                      {row.actionType}
                      {row.phaseNumber !== null && ` · phase ${row.phaseNumber}`}
                      {groupByPhase && row.phaseNumber !== null && (
                        <span className="ml-1 rounded bg-ocean-800 px-1">P{row.phaseNumber}</span>
                      )}
                    </p>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>

      <div className="flex items-center justify-between text-xs text-ocean-500">
        <span>
          {filtered.length} entr{filtered.length === 1 ? "y" : "ies"}
          {filtered.length > MAX_RENDER && ` (showing ${MAX_RENDER})`}
        </span>
        {hasNextPage && (
          <button
            onClick={() => fetchNextPage()}
            className="rounded-md border border-ocean-700 px-3 py-1 text-ocean-300 hover:bg-ocean-800"
          >
            Load older entries
          </button>
        )}
      </div>
    </div>
  );
}
