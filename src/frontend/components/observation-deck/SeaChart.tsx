"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { useVoyages } from "@/hooks/useVoyages";
import type { VoyageListItem, VoyageStatus } from "@/lib/types";
import { SeaChartCard } from "./SeaChartCard";
import { EmptyState } from "./EmptyState";

// Pipeline columns (PLAN Phase 2). CHARTED/PLANNING collapse into "Planning";
// PDD/TDD/BUILDING/REVIEWING/DEPLOYING each get a column; PAUSED rides with its
// stage via the BUILDING column fallback.
const COLUMNS: { key: string; label: string; statuses: VoyageStatus[] }[] = [
  { key: "planning", label: "Planning", statuses: ["CHARTED", "PLANNING"] },
  { key: "pdd", label: "PDD", statuses: ["PDD"] },
  { key: "tdd", label: "TDD", statuses: ["TDD"] },
  { key: "building", label: "Building", statuses: ["BUILDING", "PAUSED"] },
  { key: "reviewing", label: "Reviewing", statuses: ["REVIEWING"] },
  { key: "deploying", label: "Deploying", statuses: ["DEPLOYING"] },
];

function columnFor(status: VoyageStatus): string {
  return COLUMNS.find((c) => c.statuses.includes(status))?.key ?? "planning";
}

export function SeaChart() {
  const router = useRouter();
  const params = useSearchParams();

  // Independent query key from the Sidebar (P15).
  const active = useVoyages({ queryKey: "sea-chart-active", status: "active", limit: 50 });
  const terminal = useVoyages({ queryKey: "sea-chart-terminal", status: "terminal", limit: 20 });

  const activeVoyages = active.data?.pages.flatMap((p) => p.items) ?? [];
  const terminalVoyages = terminal.data?.pages.flatMap((p) => p.items) ?? [];

  const select = (id: string) => {
    const next = new URLSearchParams(params.toString());
    next.set("voyage", id);
    router.push(`/app/sea-chart?${next.toString()}`);
  };

  if (active.isLoading) {
    return <EmptyState title="Charting the seas…" icon="🧭" />;
  }
  if (active.error) {
    return <EmptyState title="Couldn't load voyages" hint="The stream is disconnected — check your connection." icon="⚠️" />;
  }
  if (activeVoyages.length === 0 && terminalVoyages.length === 0) {
    return <EmptyState title="No voyages yet" hint="Chart a course to send your crew sailing." />;
  }

  const byColumn = (key: string): VoyageListItem[] =>
    activeVoyages.filter((v) => columnFor(v.status) === key);

  return (
    <div className="flex h-full flex-col gap-4">
      <div className="flex flex-1 gap-3 overflow-x-auto pb-2">
        {COLUMNS.map((col) => {
          const cards = byColumn(col.key);
          return (
            <section
              key={col.key}
              className="flex w-64 shrink-0 flex-col rounded-lg bg-ocean-900/40"
              aria-label={`${col.label} column`}
            >
              <header className="flex items-center justify-between border-b border-ocean-800 px-3 py-2">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-ocean-400">
                  {col.label}
                </h3>
                <span className="rounded-full bg-ocean-800 px-2 text-[11px] text-ocean-400">
                  {cards.length}
                </span>
              </header>
              <div className="flex flex-col gap-2 p-2">
                {cards.map((v) => (
                  <SeaChartCard key={v.id} voyage={v} onSelect={select} onOpen={select} />
                ))}
              </div>
            </section>
          );
        })}
      </div>

      {active.hasNextPage && (
        <button
          onClick={() => active.fetchNextPage()}
          className="self-start rounded-md border border-ocean-700 px-3 py-1.5 text-xs text-ocean-300 hover:bg-ocean-800"
        >
          Show more voyages
        </button>
      )}

      {terminalVoyages.length > 0 && (
        <details className="rounded-lg border border-ocean-800 bg-ocean-900/30 p-3">
          <summary className="cursor-pointer text-xs font-semibold uppercase tracking-wider text-ocean-400">
            Completed & Failed ({terminalVoyages.length})
          </summary>
          <div className="mt-3 grid grid-cols-2 gap-2 md:grid-cols-3 lg:grid-cols-4">
            {terminalVoyages.map((v) => (
              <SeaChartCard key={v.id} voyage={v} onSelect={select} onOpen={select} />
            ))}
          </div>
          {terminal.hasNextPage && (
            <button
              onClick={() => terminal.fetchNextPage()}
              className="mt-2 rounded-md border border-ocean-700 px-3 py-1 text-xs text-ocean-300 hover:bg-ocean-800"
            >
              Show more
            </button>
          )}
        </details>
      )}
    </div>
  );
}
