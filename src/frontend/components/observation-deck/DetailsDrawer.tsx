"use client";

import { useState } from "react";
import { usePlaybackStore } from "@/stores/playback";
import { useDerivedState } from "@/hooks/useDerivedState";
import { useActiveVoyageEvents } from "@/hooks/useActiveVoyageEvents";

type Tab = "overview" | "events" | "timestamps";

export function DetailsDrawer() {
  const drawerVoyageId = usePlaybackStore((s) => s.drawerVoyageId);
  const close = usePlaybackStore((s) => s.closeDrawer);
  const derived = useDerivedState();
  const events = useActiveVoyageEvents();
  const [tab, setTab] = useState<Tab>("overview");

  if (!drawerVoyageId) return null;

  const firstTs = events[0]?.ts ?? null;
  const lastTs = events[events.length - 1]?.ts ?? null;

  return (
    <div className="fixed inset-0 z-40 flex justify-end" role="dialog" aria-label="Voyage details">
      <div className="flex-1 bg-black/40" onClick={close} aria-hidden />
      <aside className="flex w-96 max-w-full flex-col border-l border-ocean-800 bg-ocean-900 shadow-xl">
        <header className="flex items-center justify-between border-b border-ocean-800 px-4 py-3">
          <h3 className="text-sm font-semibold text-ocean-100">Voyage details</h3>
          <button onClick={close} className="text-ocean-400 hover:text-ocean-100" aria-label="Close details">
            ✕
          </button>
        </header>

        <nav className="flex gap-1 border-b border-ocean-800 px-2 py-2 text-xs">
          {(["overview", "events", "timestamps"] as Tab[]).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`rounded px-2 py-1 capitalize ${
                tab === t ? "bg-ocean-700 text-ocean-50" : "text-ocean-400 hover:bg-ocean-800"
              }`}
            >
              {t}
            </button>
          ))}
        </nav>

        <div className="flex-1 overflow-auto p-4 text-sm">
          {tab === "overview" && (
            <div className="space-y-3">
              <Row label="Status" value={derived.status ?? "—"} />
              <Row label="Active crew" value={derived.activeCrew ?? "idle"} />
              <Row label="Completed phases" value={derived.completedPhases.join(", ") || "none"} />
              {derived.failure && (
                <div className="rounded border border-rose-700 bg-rose-500/10 p-2 text-rose-200">
                  <p className="font-medium">Failure at {derived.failure.stage}</p>
                  <p className="text-xs">{derived.failure.code}: {derived.failure.message}</p>
                </div>
              )}
              <div>
                <p className="mb-1 text-xs font-medium uppercase tracking-wide text-ocean-400">
                  Phase status
                </p>
                <table className="w-full text-xs">
                  <tbody>
                    {Object.entries(derived.phaseStatus).map(([n, s]) => (
                      <tr key={n} className="border-b border-ocean-800/50">
                        <td className="py-1 text-ocean-400">Phase {n}</td>
                        <td className="py-1 text-right text-ocean-200">{s}</td>
                      </tr>
                    ))}
                    {Object.keys(derived.phaseStatus).length === 0 && (
                      <tr>
                        <td className="py-1 text-ocean-500">No builds yet</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {tab === "events" && (
            <ul className="space-y-1 text-xs">
              {events.slice(-50).reverse().map((e) => (
                <li key={e.event_id} className="rounded bg-ocean-950/50 px-2 py-1">
                  <span className="text-ocean-400">{e.source_role}</span>{" "}
                  <span className="text-ocean-200">{e.type}</span>
                </li>
              ))}
              {events.length === 0 && <li className="text-ocean-500">No events yet.</li>}
            </ul>
          )}

          {tab === "timestamps" && (
            <div className="space-y-3">
              <Row label="First event" value={firstTs ? new Date(firstTs).toLocaleString() : "—"} />
              <Row label="Last activity" value={lastTs ? new Date(lastTs).toLocaleString() : "—"} />
              <Row label="Events buffered" value={String(events.length)} />
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-xs uppercase tracking-wide text-ocean-400">{label}</span>
      <span className="text-ocean-100">{value}</span>
    </div>
  );
}
