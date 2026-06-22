// Deck UI store: command palette open state + focus mode (Phase 6) + the Fleet
// Switcher overlay (Phase 24).

import { create } from "zustand";

type UiState = {
  paletteOpen: boolean;
  focusMode: boolean;
  helpOpen: boolean;
  fleetOpen: boolean;
  togglePalette: () => void;
  setPalette: (open: boolean) => void;
  toggleFocusMode: () => void;
  toggleHelp: () => void;
  toggleFleet: () => void;
  setFleet: (open: boolean) => void;
};

export const useUiStore = create<UiState>((set) => ({
  paletteOpen: false,
  focusMode: false,
  helpOpen: false,
  fleetOpen: false,
  togglePalette: () => set((s) => ({ paletteOpen: !s.paletteOpen })),
  setPalette: (paletteOpen) => set({ paletteOpen }),
  toggleFocusMode: () => set((s) => ({ focusMode: !s.focusMode })),
  toggleHelp: () => set((s) => ({ helpOpen: !s.helpOpen })),
  toggleFleet: () => set((s) => ({ fleetOpen: !s.fleetOpen })),
  setFleet: (fleetOpen) => set({ fleetOpen }),
}));
