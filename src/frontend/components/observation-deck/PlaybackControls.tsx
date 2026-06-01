"use client";

import { usePlaybackStore } from "@/stores/playback";
import { useActiveVoyageEvents } from "@/hooks/useActiveVoyageEvents";

export function PlaybackControls() {
  const events = useActiveVoyageEvents();
  const mode = usePlaybackStore((s) => s.mode);
  const cursorTs = usePlaybackStore((s) => s.cursorTs);
  const scrubTo = usePlaybackStore((s) => s.scrubTo);
  const returnToLive = usePlaybackStore((s) => s.returnToLive);
  const pause = usePlaybackStore((s) => s.pause);

  if (events.length === 0) return null;

  const first = events[0].ts;
  const last = events[events.length - 1].ts;
  const value = cursorTs ?? last;
  const scrubbed = mode === "scrubbing" && cursorTs != null && cursorTs < last;

  return (
    <div className="flex items-center gap-3 border-t border-ocean-800 bg-ocean-900/80 px-6 py-2 text-xs text-ocean-300">
      <button
        onClick={mode === "live" ? pause : returnToLive}
        className="rounded border border-ocean-700 px-2 py-1 hover:bg-ocean-800"
      >
        {mode === "live" ? "⏸ Pause" : "▶ Return to live"}
      </button>
      <span className="text-ocean-500" title="earliest event in buffer">
        {new Date(first).toLocaleTimeString()}
      </span>
      <input
        type="range"
        min={first}
        max={last}
        value={value}
        onChange={(e) => scrubTo(Number(e.target.value))}
        className="h-1 flex-1 accent-emerald-400"
        aria-label="Playback scrubber"
        role="slider"
      />
      <span className="text-ocean-500">{new Date(last).toLocaleTimeString()}</span>
      {scrubbed && <span className="text-amber-300">scrubbing</span>}
    </div>
  );
}
