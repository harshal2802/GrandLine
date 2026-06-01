// Voyage pipeline status over GET /voyages/{id}/status. Feeds the store so the
// stream hook can honor terminal closure (P10).

"use client";

import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { apiFetch } from "@/lib/api";
import type { VoyageStatus } from "@/lib/types";
import { useVoyageStore } from "@/stores/voyage";

export type PipelineStatus = {
  voyage_id: string;
  status: VoyageStatus;
  current_stage?: string | null;
  phase_status?: Record<string, string>;
};

export function useVoyageStatus(voyageId: string | null) {
  const query = useQuery<PipelineStatus>({
    queryKey: ["voyage-status", voyageId],
    queryFn: () => apiFetch<PipelineStatus>(`/voyages/${voyageId}/status`),
    enabled: !!voyageId,
    refetchInterval: 15_000,
  });

  // Mirror status into the store so P10 terminal handling kicks in.
  useEffect(() => {
    if (voyageId && query.data?.status) {
      useVoyageStore.getState().setStatus(voyageId, query.data.status);
    }
  }, [voyageId, query.data?.status]);

  return query;
}
