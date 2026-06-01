"use client";

import { useVoyageStore } from "@/stores/voyage";
import type { ConnectionState as ConnState } from "@/lib/types";

const LABELS: Record<ConnState, string> = {
  idle: "Idle",
  connecting: "Connecting…",
  open: "Live",
  reconnecting: "Reconnecting…",
  "terminal-idle": "Voyage ended",
  closed: "Disconnected",
};

const DOT: Record<ConnState, string> = {
  idle: "bg-ocean-600",
  connecting: "bg-amber-400 animate-pulse",
  open: "bg-emerald-400",
  reconnecting: "bg-amber-400 animate-pulse",
  "terminal-idle": "bg-ocean-400",
  closed: "bg-rose-500",
};

export function ConnectionState({ onReconnect }: { onReconnect?: () => void }) {
  const state = useVoyageStore((s) => s.connectionState);
  const transport = useVoyageStore((s) => s.transport);
  const activeVoyageId = useVoyageStore((s) => s.activeVoyageId);
  const lastEventTs = useVoyageStore((s) =>
    activeVoyageId ? s.buffers[activeVoyageId]?.lastEventTs ?? null : null,
  );

  const canRetry = state === "closed";
  const terminal = state === "terminal-idle";

  return (
    <div className="flex items-center gap-2 text-xs text-ocean-300" role="status" aria-live="polite">
      <span className={`inline-block h-2 w-2 rounded-full ${DOT[state]}`} aria-hidden />
      <span className="font-medium text-ocean-200">{LABELS[state]}</span>
      {state === "open" && (
        <span className="uppercase tracking-wide text-ocean-500">{transport}</span>
      )}
      {lastEventTs && (
        <span className="text-ocean-500" title={new Date(lastEventTs).toISOString()}>
          · last {relative(lastEventTs)}
        </span>
      )}
      {canRetry && onReconnect && (
        <button
          onClick={onReconnect}
          className="rounded border border-ocean-700 px-2 py-0.5 text-ocean-200 hover:bg-ocean-800"
        >
          Reconnect
        </button>
      )}
      {terminal && (
        <span
          className="text-ocean-500"
          title="voyage is in a terminal state — close and re-open the deck to retry"
        >
          (read-only)
        </span>
      )}
    </div>
  );
}

function relative(ts: number): string {
  const s = Math.round((Date.now() - ts) / 1000);
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  return `${Math.round(m / 60)}h ago`;
}
