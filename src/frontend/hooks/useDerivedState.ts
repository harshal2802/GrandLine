// Reduces the active voyage's events into playback state, respecting the
// playback cursor (P5). When scrubbing, only events with ts <= cursorTs reduce.

"use client";

import { useMemo } from "react";
import { useActiveVoyageEvents } from "@/hooks/useActiveVoyageEvents";
import { usePlaybackStore } from "@/stores/playback";
import { reducePlayback, type PlaybackState } from "@/lib/playback/reducer";

export function useDerivedState(): PlaybackState {
  const events = useActiveVoyageEvents();
  const cursorTs = usePlaybackStore((s) => s.cursorTs);

  return useMemo(() => {
    const slice = cursorTs == null ? events : events.filter((e) => e.ts <= cursorTs);
    return reducePlayback(slice);
  }, [events, cursorTs]);
}
