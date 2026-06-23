"use client";

import { useEffect, useRef } from "react";
import { useVoyageStore } from "@/stores/voyage";
import { usePreview, useStartPreview, useStopPreview } from "@/hooks/usePreview";
import { usePreviewLogs } from "@/hooks/usePreviewLogs";

// Phase B2 — the embedded preview surface. When no preview is running it shows a
// "Start preview" button; when one is running it embeds the Cabin-run app in a
// sandboxed iframe (pointed at PreviewInfo.url) with a Stop control, an
// "open in new tab" link, and a live logs pane (B1) with follow/pause. The app runs
// INSIDE the user's gVisor Cabin — this view never sees a secret, only the URL +
// app stdout/stderr. The active voyage comes from the store.
export function PreviewPanel() {
  const voyageId = useVoyageStore((s) => s.activeVoyageId);

  const previewQuery = usePreview(voyageId);
  const startMutation = useStartPreview(voyageId);
  const stopMutation = useStopPreview(voyageId);

  const preview = previewQuery.data ?? null;
  const isRunning = preview !== null && preview.status !== "stopped" && preview.status !== "failed";

  // Stream logs only while a preview is running.
  const { lines, connection, follow, setFollow, clear } = usePreviewLogs(
    voyageId,
    isRunning,
  );

  if (!voyageId) {
    return (
      <div className="rounded-lg border border-ocean-800 bg-ocean-900/40 p-6 text-sm text-ocean-300">
        Select a voyage to preview its built app.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-lg font-semibold text-ocean-100">Preview</h1>
          <p className="text-xs text-ocean-400">
            Run the crew&apos;s built app inside your Cabin and watch it live.
          </p>
        </div>
        <PreviewControls
          isRunning={isRunning}
          isLoading={previewQuery.isLoading}
          starting={startMutation.isPending}
          stopping={stopMutation.isPending}
          onStart={() => startMutation.mutate()}
          onStop={() => stopMutation.mutate()}
        />
      </header>

      {previewQuery.isError && (
        <div className="rounded-md border border-rose-700/50 bg-rose-900/20 px-3 py-2 text-sm text-rose-200">
          Could not load preview status. Try again.
        </div>
      )}
      {startMutation.isError && (
        <div className="rounded-md border border-rose-700/50 bg-rose-900/20 px-3 py-2 text-sm text-rose-200">
          {startMutation.error?.message ?? "Failed to start the preview."}
        </div>
      )}

      {previewQuery.isLoading ? (
        <div className="rounded-lg border border-ocean-800 bg-ocean-900/40 p-6 text-sm text-ocean-300">
          Loading preview…
        </div>
      ) : isRunning && preview ? (
        <RunningPreview
          url={preview.url}
          status={preview.status}
          lines={lines}
          connection={connection}
          follow={follow}
          setFollow={setFollow}
          clear={clear}
        />
      ) : (
        <div className="rounded-lg border border-dashed border-ocean-800 bg-ocean-900/40 p-8 text-center text-sm text-ocean-300">
          No preview is running for this voyage.
          {preview?.status === "failed" && (
            <span className="ml-1 text-rose-300">The last preview failed.</span>
          )}
        </div>
      )}
    </div>
  );
}

interface PreviewControlsProps {
  isRunning: boolean;
  isLoading: boolean;
  starting: boolean;
  stopping: boolean;
  onStart: () => void;
  onStop: () => void;
}

function PreviewControls({
  isRunning,
  isLoading,
  starting,
  stopping,
  onStart,
  onStop,
}: PreviewControlsProps) {
  if (isLoading) return null;
  if (isRunning) {
    return (
      <button
        type="button"
        onClick={onStop}
        disabled={stopping}
        className="rounded-md border border-rose-700 bg-rose-900/30 px-3 py-1.5 text-sm text-rose-100 hover:bg-rose-900/50 disabled:opacity-50"
      >
        {stopping ? "Stopping…" : "Stop preview"}
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={onStart}
      disabled={starting}
      className="rounded-md border border-emerald-700 bg-emerald-900/30 px-3 py-1.5 text-sm text-emerald-100 hover:bg-emerald-900/50 disabled:opacity-50"
    >
      {starting ? "Starting…" : "Start preview"}
    </button>
  );
}

interface RunningPreviewProps {
  url: string;
  status: string;
  lines: string[];
  connection: string;
  follow: boolean;
  setFollow: (follow: boolean) => void;
  clear: () => void;
}

function RunningPreview({
  url,
  status,
  lines,
  connection,
  follow,
  setFollow,
  clear,
}: RunningPreviewProps) {
  return (
    <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
      <section className="lg:col-span-2 space-y-2">
        <div className="flex items-center justify-between gap-2 text-xs text-ocean-400">
          <span className="inline-flex items-center gap-1.5">
            <span
              className={`h-2 w-2 rounded-full ${
                status === "running" ? "bg-emerald-400" : "bg-amber-400"
              }`}
            />
            {status}
          </span>
          <a
            href={url}
            target="_blank"
            rel="noreferrer noopener"
            className="text-ocean-300 underline hover:text-ocean-100"
          >
            Open in new tab ↗
          </a>
        </div>
        <iframe
          title="App preview"
          src={url}
          sandbox="allow-scripts allow-same-origin allow-forms allow-popups"
          className="h-[60vh] w-full rounded-lg border border-ocean-800 bg-white"
        />
      </section>
      <LogsPane
        lines={lines}
        connection={connection}
        follow={follow}
        setFollow={setFollow}
        clear={clear}
      />
    </div>
  );
}

interface LogsPaneProps {
  lines: string[];
  connection: string;
  follow: boolean;
  setFollow: (follow: boolean) => void;
  clear: () => void;
}

function LogsPane({ lines, connection, follow, setFollow, clear }: LogsPaneProps) {
  const scrollRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll to the newest line while following.
  useEffect(() => {
    if (follow && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines, follow]);

  return (
    <section className="flex flex-col rounded-lg border border-ocean-800 bg-ocean-950">
      <div className="flex items-center justify-between gap-2 border-b border-ocean-800 px-3 py-2 text-xs text-ocean-300">
        <span className="inline-flex items-center gap-1.5">
          <span
            className={`h-2 w-2 rounded-full ${
              connection === "open" ? "bg-emerald-400" : "bg-ocean-600"
            }`}
          />
          Logs
        </span>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setFollow(!follow)}
            className="rounded border border-ocean-700 px-2 py-0.5 hover:bg-ocean-800"
          >
            {follow ? "Pause" : "Follow"}
          </button>
          <button
            type="button"
            onClick={clear}
            className="rounded border border-ocean-700 px-2 py-0.5 hover:bg-ocean-800"
          >
            Clear
          </button>
        </div>
      </div>
      <div
        ref={scrollRef}
        className="h-[60vh] overflow-auto px-3 py-2 font-mono text-xs leading-relaxed text-ocean-200"
      >
        {lines.length === 0 ? (
          <p className="text-ocean-500">Waiting for log output…</p>
        ) : (
          lines.map((line, i) => (
            <div key={i} className="whitespace-pre-wrap break-all">
              {line}
            </div>
          ))
        )}
      </div>
    </section>
  );
}
