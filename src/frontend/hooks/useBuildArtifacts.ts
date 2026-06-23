// Build-artifacts hook over GET /voyages/{id}/build-artifacts (Phase A1 — the
// "Changes" view). The phase_number query param is OMITTED so we get artifacts
// for ALL phases in one read; the component groups them by phase client-side.
// The Shipwright already stores + serves every generated file, so this is the
// always-available, no-git code browser.

"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { BuildArtifact } from "@/lib/types";

type BuildArtifactListResponse = {
  voyage_id: string;
  phase_number: number | null;
  artifacts: BuildArtifact[];
};

export function useBuildArtifacts(voyageId: string | null) {
  return useQuery<BuildArtifact[]>({
    queryKey: ["build-artifacts", voyageId],
    queryFn: async () => {
      const res = await apiFetch<BuildArtifactListResponse>(
        `/voyages/${voyageId}/build-artifacts`,
      );
      return res.artifacts;
    },
    enabled: !!voyageId,
    staleTime: 30_000,
  });
}
