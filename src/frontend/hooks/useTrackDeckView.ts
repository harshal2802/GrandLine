// Records the active deck view per voyage (Phase 24 "Fleet Switcher"), so the
// switcher can restore exactly where you left a voyage. Each view page calls
// `useTrackDeckView(view)` on mount. No-op when there's no active voyage.

"use client";

import { useEffect } from "react";
import { useSearchParams } from "next/navigation";
import { useDeckStateStore, type DeckView } from "@/stores/deckState";

export function useTrackDeckView(view: DeckView): void {
  const params = useSearchParams();
  const voyageId = params.get("voyage");

  useEffect(() => {
    if (!voyageId) return;
    useDeckStateStore.getState().setLastView(voyageId, view);
  }, [voyageId, view]);
}
