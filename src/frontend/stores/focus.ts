// Cross-view focus store (Decision 9). Hovering a phase/crew anywhere
// highlights the matching element in the other views. Selection persists;
// hover does not.

import { create } from "zustand";

type FocusState = {
  hoveredPhase: number | null;
  hoveredCrew: string | null;
  selectedEventId: string | null;
  setHoveredPhase: (n: number | null) => void;
  setHoveredCrew: (c: string | null) => void;
  setSelectedEvent: (id: string | null) => void;
};

export const useFocusStore = create<FocusState>((set) => ({
  hoveredPhase: null,
  hoveredCrew: null,
  selectedEventId: null,
  setHoveredPhase: (hoveredPhase) => set({ hoveredPhase }),
  setHoveredCrew: (hoveredCrew) => set({ hoveredCrew }),
  setSelectedEvent: (selectedEventId) => set({ selectedEventId }),
}));
