// Playback store (Decision 7). Local scrubbing over the live ring buffer.
// On voyage switch: discard state, return to live (resolved open question).

import { create } from "zustand";

export type PlaybackMode = "live" | "paused" | "scrubbing";

type PlaybackState = {
  mode: PlaybackMode;
  cursorTs: number | null; // null = live (no cutoff)
  drawerVoyageId: string | null; // details drawer target

  pause: () => void;
  resume: () => void;
  scrubTo: (ts: number) => void;
  returnToLive: () => void;
  openDrawer: (voyageId: string) => void;
  closeDrawer: () => void;
  resetForVoyage: () => void;
};

export const usePlaybackStore = create<PlaybackState>((set) => ({
  mode: "live",
  cursorTs: null,
  drawerVoyageId: null,

  pause: () => set({ mode: "paused" }),
  resume: () => set({ mode: "live", cursorTs: null }),
  scrubTo: (ts) => set({ mode: "scrubbing", cursorTs: ts }),
  returnToLive: () => set({ mode: "live", cursorTs: null }),
  openDrawer: (voyageId) => set({ drawerVoyageId: voyageId }),
  closeDrawer: () => set({ drawerVoyageId: null }),
  resetForVoyage: () => set({ mode: "live", cursorTs: null }),
}));
