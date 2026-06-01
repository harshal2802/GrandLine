// Ship's Log data hook over GET /voyages/{id}/crew-actions (CONTRACTS P6, P9).
//
// Cursor pagination (P6). Reconciliation (P9): refetch first page on WS
// reconnect and window focus; periodic poll while the voyage is active,
// short-circuited if a WS event arrived in the poll window.

"use client";

import {
  useInfiniteQuery,
  useQueryClient,
  type InfiniteData,
} from "@tanstack/react-query";
import { useEffect } from "react";
import { apiFetch } from "@/lib/api";
import type { CrewActionRead, Paginated } from "@/lib/types";
import { useVoyageStore } from "@/stores/voyage";
import { isTerminal } from "@/lib/types";

export function useCrewActions(opts: {
  voyageId: string | null;
  limit?: number;
  pollMs?: number;
}) {
  const { voyageId, limit = 200, pollMs = 60_000 } = opts;
  const queryClient = useQueryClient();

  const query = useInfiniteQuery<
    Paginated<CrewActionRead>,
    Error,
    InfiniteData<Paginated<CrewActionRead>>,
    [string, string | null],
    string | null
  >({
    queryKey: ["crew-actions", voyageId],
    initialPageParam: null,
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams();
      params.set("limit", String(limit));
      if (pageParam) params.set("cursor", pageParam);
      return apiFetch<Paginated<CrewActionRead>>(
        `/voyages/${voyageId}/crew-actions?${params.toString()}`,
      );
    },
    getNextPageParam: (last) => last.nextCursor,
    enabled: !!voyageId,
    refetchOnWindowFocus: true,
    staleTime: 10_000,
  });

  // Periodic poll while active, short-circuited by a recent WS event (P9).
  useEffect(() => {
    if (!voyageId || pollMs <= 0) return;
    const interval = setInterval(() => {
      const buf = useVoyageStore.getState().buffers[voyageId];
      if (buf && isTerminal(buf.status)) return; // stop polling terminal voyages
      const recentWs =
        buf?.lastEventTs != null && Date.now() - buf.lastEventTs < pollMs;
      if (recentWs) return; // a WS event already kept us fresh
      void queryClient.invalidateQueries({ queryKey: ["crew-actions", voyageId] });
    }, pollMs);
    return () => clearInterval(interval);
  }, [voyageId, pollMs, queryClient]);

  return query;
}
