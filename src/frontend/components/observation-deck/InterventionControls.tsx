"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useVoyageStore } from "@/stores/voyage";
import { isTerminal } from "@/lib/types";
import {
  cancelVoyage,
  injectContext,
  pauseVoyage,
  resumeVoyage,
} from "@/lib/intervention";

// Fleet-admiral control bar (Phase 17). Pause/Resume/Cancel + Inject context,
// with confirmation for the destructive Cancel.
export function InterventionControls({ voyageId }: { voyageId: string }) {
  const status = useVoyageStore((s) => s.buffers[voyageId]?.status);
  const queryClient = useQueryClient();

  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [showInject, setShowInject] = useState(false);
  const [injectText, setInjectText] = useState("");

  const paused = status === "PAUSED";
  const terminal = isTerminal(status);

  const refresh = () => {
    queryClient.invalidateQueries({ queryKey: ["voyage-status", voyageId] });
    queryClient.invalidateQueries({ queryKey: ["crew-actions", voyageId] });
  };

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Action failed");
    } finally {
      setBusy(false);
    }
  };

  if (terminal) return null;

  return (
    <div className="flex items-center gap-2 text-xs">
      {paused ? (
        <button
          disabled={busy}
          onClick={() => run(() => resumeVoyage(voyageId))}
          className="rounded border border-emerald-700 px-2 py-1 text-emerald-300 hover:bg-emerald-900/40 disabled:opacity-50"
        >
          ▶ Resume
        </button>
      ) : (
        <button
          disabled={busy}
          onClick={() => run(() => pauseVoyage(voyageId))}
          className="rounded border border-amber-700 px-2 py-1 text-amber-300 hover:bg-amber-900/40 disabled:opacity-50"
        >
          ❚❚ Pause
        </button>
      )}

      <button
        disabled={busy}
        onClick={() => setShowInject(true)}
        className="rounded border border-ocean-700 px-2 py-1 text-ocean-300 hover:bg-ocean-800 disabled:opacity-50"
      >
        ✎ Inject
      </button>

      <button
        disabled={busy}
        onClick={() => setConfirmCancel(true)}
        className="rounded border border-rose-700 px-2 py-1 text-rose-300 hover:bg-rose-900/40 disabled:opacity-50"
      >
        ✕ Cancel
      </button>

      {error && <span className="text-rose-400">{error}</span>}

      {/* Cancel confirmation (destructive) */}
      {confirmCancel && (
        <Modal title="Cancel voyage?" onClose={() => setConfirmCancel(false)}>
          <p className="text-sm text-ocean-300">
            This stops all crew and marks the voyage CANCELLED. The Vivre Card
            state is preserved, but the voyage cannot be resumed.
          </p>
          <div className="mt-4 flex justify-end gap-2">
            <button
              onClick={() => setConfirmCancel(false)}
              className="rounded border border-ocean-700 px-3 py-1 text-ocean-300 hover:bg-ocean-800"
            >
              Keep sailing
            </button>
            <button
              onClick={() => {
                setConfirmCancel(false);
                run(() => cancelVoyage(voyageId));
              }}
              className="rounded bg-rose-600 px-3 py-1 text-white hover:bg-rose-500"
            >
              Cancel voyage
            </button>
          </div>
        </Modal>
      )}

      {/* Inject context */}
      {showInject && (
        <Modal title="Inject context" onClose={() => setShowInject(false)}>
          <p className="mb-2 text-sm text-ocean-400">
            Add instructions to the crew&apos;s context for the rest of the voyage.
          </p>
          <textarea
            value={injectText}
            onChange={(e) => setInjectText(e.target.value)}
            rows={4}
            className="w-full rounded border border-ocean-700 bg-ocean-950 px-2 py-1 text-sm text-ocean-100 outline-none focus:border-ocean-400"
            placeholder="e.g. prefer PostgreSQL over SQLite for persistence"
          />
          <div className="mt-3 flex justify-end gap-2">
            <button
              onClick={() => setShowInject(false)}
              className="rounded border border-ocean-700 px-3 py-1 text-sm text-ocean-300 hover:bg-ocean-800"
            >
              Cancel
            </button>
            <button
              disabled={!injectText.trim()}
              onClick={() => {
                const text = injectText.trim();
                setShowInject(false);
                setInjectText("");
                run(() => injectContext(voyageId, text));
              }}
              className="rounded bg-ocean-500 px-3 py-1 text-sm text-ocean-950 hover:bg-ocean-400 disabled:opacity-50"
            >
              Inject
            </button>
          </div>
        </Modal>
      )}
    </div>
  );
}

function Modal({
  title,
  children,
  onClose,
}: {
  title: string;
  children: React.ReactNode;
  onClose: () => void;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-label={title}>
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <div className="relative w-full max-w-md rounded-xl border border-ocean-700 bg-ocean-900 p-5 shadow-2xl">
        <h3 className="mb-3 text-sm font-semibold text-ocean-100">{title}</h3>
        {children}
      </div>
    </div>
  );
}
