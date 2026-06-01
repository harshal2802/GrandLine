// Deck UI store: command palette open state + focus mode (Phase 6).

import { create } from "zustand";

type UiState = {
  paletteOpen: boolean;
  focusMode: boolean;
  helpOpen: boolean;
  togglePalette: () => void;
  setPalette: (open: boolean) => void;
  toggleFocusMode: () => void;
  toggleHelp: () => void;
};

export const useUiStore = create<UiState>((set) => ({
  paletteOpen: false,
  focusMode: false,
  helpOpen: false,
  togglePalette: () => set((s) => ({ paletteOpen: !s.paletteOpen })),
  setPalette: (paletteOpen) => set({ paletteOpen }),
  toggleFocusMode: () => set((s) => ({ focusMode: !s.focusMode })),
  toggleHelp: () => set((s) => ({ helpOpen: !s.helpOpen })),
}));
