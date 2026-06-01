"use client";

import { useVoyageProgress } from "@/hooks/useVoyageProgress";
import { useFocusStore } from "@/stores/focus";
import { useVoyageStore } from "@/stores/voyage";
import type { VoyageListItem } from "@/lib/types";
import { StatusBadge } from "./StatusBadge";

function relativeTime(ts: number | null): string {
  if (!ts) return "no events yet";
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}

export function SeaChartCard({
  voyage,
  onOpen,
  onSelect,
}: {
  voyage: VoyageListItem;
  onOpen?: (id: string) => void;
  onSelect?: (id: string) => void;
}) {
  const progress = useVoyageProgress(voyage);
  const setHoveredPhase = useFocusStore((s) => s.setHoveredPhase);
  const lastEventTs = useVoyageStore(
    (s) => s.buffers[voyage.id]?.lastEventTs ?? null,
  );

  return (
    <article
      className="cursor-pointer rounded-lg border border-ocean-800 bg-ocean-900/70 p-3 transition-colors hover:border-ocean-600"
      onClick={() => onSelect?.(voyage.id)}
      aria-label={`Voyage ${voyage.title}, status ${voyage.status}`}
    >
      <div className="flex items-start justify-between gap-2">
        <h4 className="truncate text-sm font-semibold text-ocean-100">
          {voyage.title}
        </h4>
        {progress.failure && (
          <span
            className="shrink-0 rounded bg-rose-500/20 px-1.5 py-0.5 text-[10px] font-semibold text-rose-300"
            title="This voyage has a failure"
          >
            ✕ FAILED
          </span>
        )}
      </div>

      <div className="mt-2">
        <StatusBadge status={voyage.status} />
      </div>

      {progress.totalPhases > 0 && (
        <div className="mt-2">
          <div className="mb-1 flex items-center justify-between text-[11px] text-ocean-400">
            <span>
              {progress.phasesBuilt}/{progress.totalPhases} phases
            </span>
            <span>{progress.percentComplete}%</span>
          </div>
          <div className="h-1.5 w-full overflow-hidden rounded-full bg-ocean-800">
            <div
              className="h-full rounded-full bg-emerald-400 transition-all"
              style={{ width: `${progress.percentComplete}%` }}
            />
          </div>
          {/* Cross-view: hovering a phase highlights it elsewhere. */}
          <div className="mt-1 flex flex-wrap gap-1">
            {Object.keys(voyage.phase_status).map((p) => (
              <span
                key={p}
                onMouseEnter={() => setHoveredPhase(Number(p))}
                onMouseLeave={() => setHoveredPhase(null)}
                className="rounded bg-ocean-800 px-1 text-[10px] text-ocean-400 hover:bg-ocean-700"
              >
                {p}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-2 flex items-center justify-between text-[11px] text-ocean-500">
        <span title={lastEventTs ? new Date(lastEventTs).toISOString() : undefined}>
          {relativeTime(lastEventTs)}
        </span>
        {onOpen && (
          <button
            onClick={(e) => {
              e.stopPropagation();
              onOpen(voyage.id);
            }}
            className="text-ocean-300 underline hover:text-ocean-100"
          >
            Open details
          </button>
        )}
      </div>
    </article>
  );
}
