// Returns the active voyage's events, sorted canonically (P3). Re-renders when
// the underlying buffer changes (ingest replaces the events Map by reference).

"use client";

import { useMemo } from "react";
import { useVoyageStore } from "@/stores/voyage";
import { compareEnvelopes } from "@/lib/eventEnvelope";
import type { EventEnvelope } from "@/lib/types";

export function useActiveVoyageEvents(): EventEnvelope[] {
  const activeId = useVoyageStore((s) => s.activeVoyageId);
  const buffer = useVoyageStore((s) => (activeId ? s.buffers[activeId] : undefined));

  return useMemo(() => {
    if (!buffer) return [];
    return Array.from(buffer.events.values()).sort(compareEnvelopes);
  }, [buffer]);
}
