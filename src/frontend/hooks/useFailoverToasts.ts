// Watches the active voyage's live events for Dial System failovers
// (provider_switched) and raises a toast so a mid-voyage switch isn't silent
// in the deck (#54). Replays don't toast (P2), mirroring CrewMap's animation.

"use client";

import { useEffect, useRef } from "react";
import { useActiveVoyageEvents } from "@/hooks/useActiveVoyageEvents";
import { useToastStore } from "@/stores/toast";

export function useFailoverToasts(): void {
  const events = useActiveVoyageEvents();
  const push = useToastStore((s) => s.push);
  const seen = useRef(0);

  useEffect(() => {
    if (events.length <= seen.current) {
      seen.current = events.length;
      return;
    }
    const fresh = events.slice(seen.current);
    seen.current = events.length;

    for (const e of fresh) {
      if (e.isReplay || e.type !== "provider_switched") continue;
      const payload = e.payload as Record<string, unknown>;
      const provider =
        typeof payload.new_provider === "string" ? payload.new_provider : "another provider";
      const model = typeof payload.new_model === "string" ? payload.new_model : null;
      push({
        tone: "warn",
        title: `⚡ ${e.source_role} switched provider`,
        body: model ? `Now routing through ${provider}/${model}` : `Now routing through ${provider}`,
      });
    }
  }, [events, push]);
}
