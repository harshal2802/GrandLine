"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useVoyages } from "@/hooks/useVoyages";
import { useVoyageStore } from "@/stores/voyage";
import { useDeckStateStore } from "@/stores/deckState";
import { useUiStore } from "@/stores/ui";
import type { VoyageListItem } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";
import { EmptyState } from "./EmptyState";

// Order voyages with the active voyage's recents first (the voyage store's LRU
// `visitedOrder`), then the remaining query order — so the ships you've been
// watching are at your fingertips.
function orderByRecents(
  voyages: VoyageListItem[],
  visitedOrder: string[],
): VoyageListItem[] {
  const rank = new Map(visitedOrder.map((id, i) => [id, i]));
  return [...voyages].sort((a, b) => {
    const ra = rank.has(a.id) ? rank.get(a.id)! : Number.POSITIVE_INFINITY;
    const rb = rank.has(b.id) ? rank.get(b.id)! : Number.POSITIVE_INFINITY;
    return ra - rb;
  });
}

export function FleetSwitcher() {
  const router = useRouter();
  const open = useUiStore((s) => s.fleetOpen);
  const setFleet = useUiStore((s) => s.setFleet);

  const activeVoyageId = useVoyageStore((s) => s.activeVoyageId);
  const visitedOrder = useVoyageStore((s) => s.visitedOrder);

  const { data, isLoading, error } = useVoyages({
    queryKey: "fleet-switcher",
    limit: 50,
    enabled: open,
  });

  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (open) {
      setQuery("");
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const voyages = useMemo(
    () => data?.pages.flatMap((p) => p.items) ?? [],
    [data],
  );

  const ordered = useMemo(
    () => orderByRecents(voyages, visitedOrder),
    [voyages, visitedOrder],
  );

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return ordered;
    return ordered.filter((v) => v.title.toLowerCase().includes(q));
  }, [ordered, query]);

  const switchTo = (id: string) => {
    // The voyage store owns the switch primitive (events + LRU); we layer view
    // restoration on top.
    useVoyageStore.getState().selectVoyage(id);
    const { lastView } = useDeckStateStore.getState().getDeckState(id);
    setFleet(false);
    router.push(`/app/${lastView}?voyage=${id}`);
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-32"
      role="dialog"
      aria-label="Fleet Switcher"
    >
      <div
        className="absolute inset-0 bg-black/50"
        onClick={() => setFleet(false)}
        aria-hidden
      />
      <div className="relative w-full max-w-md overflow-hidden rounded-xl border border-ocean-700 bg-ocean-900 shadow-2xl">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Switch voyage…"
          aria-label="Filter voyages"
          className="w-full border-b border-ocean-800 bg-ocean-950 px-4 py-3 text-ocean-100 outline-none"
        />
        <div className="max-h-72 overflow-auto py-1">
          {isLoading && (
            <p className="px-4 py-3 text-sm text-ocean-500">Hailing the fleet…</p>
          )}
          {error && (
            <p className="px-4 py-3 text-sm text-rose-400">
              Couldn&apos;t reach the fleet
            </p>
          )}
          {!isLoading && !error && filtered.length === 0 && (
            <EmptyState
              title={query ? "No matching voyages" : "No voyages yet"}
              hint={query ? "Try a different name." : "Chart a course to begin."}
              icon="⚓"
            />
          )}
          {!isLoading && !error && filtered.length > 0 && (
            <ul>
              {filtered.map((v) => (
                <li key={v.id}>
                  <button
                    onClick={() => switchTo(v.id)}
                    aria-current={activeVoyageId === v.id ? "true" : undefined}
                    className={`flex w-full items-center justify-between gap-3 px-4 py-2.5 text-left transition-colors ${
                      activeVoyageId === v.id
                        ? "bg-ocean-700/60 text-ocean-50"
                        : "text-ocean-200 hover:bg-ocean-800"
                    }`}
                  >
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">
                      {activeVoyageId === v.id && (
                        <span className="mr-1 text-ocean-400" aria-hidden>
                          ⚓
                        </span>
                      )}
                      {v.title}
                    </span>
                    <StatusBadge status={v.status} />
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
