// Preview status + start/stop hooks (Phases B0/B2) over the B0 backend.
//
// usePreview reads the running preview via GET /voyages/{id}/preview. The backend
// returns 404 when nothing is running, which we map to `null` (a normal empty state,
// not an error) so the panel can show a Start button. start/stop are mutations that
// invalidate the status query so the UI flips immediately.

"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError } from "@/lib/api";
import { getPreview, startPreview, stopPreview, type PreviewInfo } from "@/lib/preview";

export function previewQueryKey(voyageId: string | null) {
  return ["preview", voyageId] as const;
}

// Status query: `null` means "no preview running" (404), which is a valid empty
// state. Any other error surfaces via `isError`.
export function usePreview(voyageId: string | null) {
  return useQuery<PreviewInfo | null>({
    queryKey: previewQueryKey(voyageId),
    queryFn: async () => {
      try {
        return await getPreview(voyageId as string);
      } catch (e) {
        if (e instanceof ApiError && e.status === 404) return null;
        throw e;
      }
    },
    enabled: !!voyageId,
    retry: false,
    refetchInterval: 10_000,
  });
}

export function useStartPreview(voyageId: string | null) {
  const queryClient = useQueryClient();
  return useMutation<PreviewInfo, Error, void>({
    mutationFn: () => startPreview(voyageId as string),
    onSuccess: (info) => {
      queryClient.setQueryData(previewQueryKey(voyageId), info);
      void queryClient.invalidateQueries({ queryKey: previewQueryKey(voyageId) });
    },
  });
}

export function useStopPreview(voyageId: string | null) {
  const queryClient = useQueryClient();
  return useMutation<void, Error, void>({
    mutationFn: () => stopPreview(voyageId as string),
    onSuccess: () => {
      queryClient.setQueryData(previewQueryKey(voyageId), null);
      void queryClient.invalidateQueries({ queryKey: previewQueryKey(voyageId) });
    },
  });
}
