"use client";

import { useEffect, useState } from "react";
import { usePlaybackStore } from "@/stores/playback";
import { useDerivedState } from "@/hooks/useDerivedState";
import { useActiveVoyageEvents } from "@/hooks/useActiveVoyageEvents";
import { latestDeployment, rollbackDeployment } from "@/lib/deployments";
import { DialPanel } from "./DialPanel";

type Tab = "overview" | "events" | "dial" | "timestamps";

export function DetailsDrawer() {
  const drawerVoyageId = usePlaybackStore((s) => s.drawerVoyageId);
  const close = usePlaybackStore((s) => s.closeDrawer);
  const derived = useDerivedState();
  const events = useActiveVoyageEvents();
  const [tab, setTab] = useState<Tab>("overview");

  const deployment = latestDeployment(events);
  const [rbBusy, setRbBusy] = useState(false);
  const [rbError, setRbError] = useState<string | null>(null);
  const [rbDone, setRbDone] = useState(false);
  const [confirmRollback, setConfirmRollback] = useState(false);

  // The drawer is mounted once and reused across voyages, so reset rollback
  // state when it switches voyages — otherwise voyage A's "Rolled back" leaks
  // onto voyage B's panel.
  useEffect(() => {
    setRbBusy(false);
    setRbError(null);
    setRbDone(false);
    setConfirmRollback(false);
  }, [drawerVoyageId]);

  const rollback = async () => {
    if (!drawerVoyageId || !deployment?.tier) return;
    setRbBusy(true);
    setRbError(null);
    try {
      await rollbackDeployment(drawerVoyageId, deployment.tier);
      setRbDone(true);
    } catch (e) {
      setRbError(e instanceof Error ? e.message : "Rollback failed");
    } finally {
      setRbBusy(false);
      setConfirmRollback(false);
    }
  };

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
          {(["overview", "events", "dial", "timestamps"] as Tab[]).map((t) => (
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

              {deployment && (
                <div className="rounded border border-emerald-800 bg-emerald-500/10 p-2">
                  <p className="mb-1 text-xs font-medium uppercase tracking-wide text-emerald-300">
                    Deployment{deployment.tier ? ` · ${deployment.tier}` : ""}
                  </p>
                  {deployment.url ? (
                    <a
                      href={deployment.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="break-all text-xs text-emerald-200 underline hover:text-emerald-100"
                    >
                      {deployment.url} ↗
                    </a>
                  ) : (
                    <p className="text-xs text-emerald-200/70">No URL reported.</p>
                  )}
                  <div className="mt-2 flex items-center gap-2">
                    <button
                      disabled={rbBusy || rbDone || !deployment.tier}
                      onClick={() => setConfirmRollback(true)}
                      className="rounded border border-amber-700 px-2 py-0.5 text-xs text-amber-300 hover:bg-amber-900/40 disabled:opacity-50"
                    >
                      {rbDone ? "Rolled back" : rbBusy ? "Rolling back…" : "↩ Rollback"}
                    </button>
                    {rbError && <span className="text-xs text-rose-400">{rbError}</span>}
                  </div>
                  {confirmRollback && (
                    <div className="mt-2 rounded border border-amber-700 bg-amber-500/10 p-2">
                      <p className="text-xs text-amber-200">
                        Roll back the latest <strong>{deployment.tier}</strong>{" "}
                        deployment?
                      </p>
                      <div className="mt-2 flex justify-end gap-2">
                        <button
                          onClick={() => setConfirmRollback(false)}
                          className="rounded border border-ocean-700 px-2 py-0.5 text-xs text-ocean-300 hover:bg-ocean-800"
                        >
                          Cancel
                        </button>
                        <button
                          onClick={() => void rollback()}
                          className="rounded bg-amber-600 px-2 py-0.5 text-xs text-white hover:bg-amber-500"
                        >
                          Roll back
                        </button>
                      </div>
                    </div>
                  )}
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

          {tab === "dial" && <DialPanel voyageId={drawerVoyageId} />}

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
