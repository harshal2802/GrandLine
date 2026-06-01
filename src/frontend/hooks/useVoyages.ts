// Voyage list hook over GET /voyages (CONTRACTS P7, P15). Accepts a queryKey so
// the Sidebar and Sea Chart keep independent caches + pagination (P15).

"use client";

import {
  useInfiniteQuery,
  type InfiniteData,
} from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { Paginated, VoyageListItem } from "@/lib/types";

type StatusFilter = "active" | "terminal" | undefined;

export function useVoyages(opts: {
  queryKey: string;
  status?: StatusFilter;
  limit?: number;
  enabled?: boolean;
}) {
  const { queryKey, status, limit = 50, enabled = true } = opts;

  return useInfiniteQuery<
    Paginated<VoyageListItem>,
    Error,
    InfiniteData<Paginated<VoyageListItem>>,
    [string, StatusFilter],
    string | null
  >({
    queryKey: [queryKey, status],
    initialPageParam: null,
    queryFn: async ({ pageParam }) => {
      const params = new URLSearchParams();
      if (status) params.set("status", status);
      if (limit) params.set("limit", String(limit));
      if (pageParam) params.set("cursor", pageParam);
      const qs = params.toString();
      return apiFetch<Paginated<VoyageListItem>>(`/voyages${qs ? `?${qs}` : ""}`);
    },
    getNextPageParam: (last) => last.nextCursor,
    staleTime: 30_000,
    refetchOnWindowFocus: true,
    enabled,
  });
}
