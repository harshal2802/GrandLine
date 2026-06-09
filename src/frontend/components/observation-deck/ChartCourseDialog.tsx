"use client";

import { useState } from "react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useQueryClient } from "@tanstack/react-query";
import { createVoyage, startVoyage, MIN_TASK_LENGTH } from "@/lib/voyages";

// "Chart a course" — create a voyage (and optionally set sail immediately,
// using the mission text as the pipeline task).
export function ChartCourseDialog({ onClose }: { onClose: () => void }) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const queryClient = useQueryClient();

  const [title, setTitle] = useState("");
  const [mission, setMission] = useState("");
  const [setSail, setSetSail] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const missionTooShort = setSail && mission.trim().length < MIN_TASK_LENGTH;
  const canSubmit = title.trim().length > 0 && !missionTooShort && !busy;

  const submit = async () => {
    if (!canSubmit) return;
    setBusy(true);
    setError(null);
    try {
      const voyage = await createVoyage({
        title: title.trim(),
        description: mission.trim() || null,
      });
      if (setSail) {
        await startVoyage(voyage.id, mission.trim());
      }
      // Refresh every voyage list (sidebar + sea chart lanes).
      void queryClient.invalidateQueries({ queryKey: ["sidebar"] });
      void queryClient.invalidateQueries({ queryKey: ["sea-chart-active"] });
      void queryClient.invalidateQueries({ queryKey: ["sea-chart-terminal"] });
      // Select the new voyage in the current view.
      const next = new URLSearchParams(params.toString());
      next.set("voyage", voyage.id);
      router.push(`${pathname}?${next.toString()}`);
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to chart course");
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-label="Chart a course"
    >
      <div className="absolute inset-0 bg-black/50" onClick={onClose} aria-hidden />
      <div className="relative w-full max-w-md rounded-xl border border-ocean-700 bg-ocean-900 p-5 shadow-2xl">
        <h3 className="mb-3 text-sm font-semibold text-ocean-100">Chart a course</h3>

        <label className="mb-1 block text-xs text-ocean-400" htmlFor="voyage-title">
          Voyage title
        </label>
        <input
          id="voyage-title"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          maxLength={255}
          autoFocus
          className="mb-3 w-full rounded border border-ocean-700 bg-ocean-950 px-2 py-1.5 text-sm text-ocean-100 outline-none focus:border-ocean-400"
          placeholder="e.g. Build a URL shortener"
        />

        <label className="mb-1 block text-xs text-ocean-400" htmlFor="voyage-mission">
          Mission for the crew
        </label>
        <textarea
          id="voyage-mission"
          value={mission}
          onChange={(e) => setMission(e.target.value)}
          rows={4}
          maxLength={5000}
          className="w-full rounded border border-ocean-700 bg-ocean-950 px-2 py-1.5 text-sm text-ocean-100 outline-none focus:border-ocean-400"
          placeholder="Describe what the crew should build, test, and deploy…"
        />

        <label className="mt-3 flex items-center gap-2 text-xs text-ocean-300">
          <input
            type="checkbox"
            checked={setSail}
            onChange={(e) => setSetSail(e.target.checked)}
            className="accent-ocean-400"
          />
          Set sail immediately (start the pipeline)
        </label>
        {missionTooShort && (
          <p className="mt-1 text-xs text-amber-400">
            The mission needs at least {MIN_TASK_LENGTH} characters to set sail.
          </p>
        )}
        {error && <p className="mt-2 text-xs text-rose-400">{error}</p>}

        <div className="mt-4 flex justify-end gap-2">
          <button
            onClick={onClose}
            className="rounded border border-ocean-700 px-3 py-1 text-sm text-ocean-300 hover:bg-ocean-800"
          >
            Cancel
          </button>
          <button
            disabled={!canSubmit}
            onClick={() => void submit()}
            className="rounded bg-ocean-500 px-3 py-1 text-sm text-ocean-950 hover:bg-ocean-400 disabled:opacity-50"
          >
            {busy ? "Charting…" : setSail ? "Chart & set sail" : "Chart course"}
          </button>
        </div>
      </div>
    </div>
  );
}
