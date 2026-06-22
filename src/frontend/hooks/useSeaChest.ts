// Sea Chest connection-status hook over GET /sea-chest (Phase 0a, surfaced by the
// DialPanel in Phase C2). Returns the per-user credential statuses (claude_code /
// github) — connected + label hint only, NEVER a secret. The Disconnect action in the
// DialPanel invalidates ["sea-chest"] to refetch after a DELETE.

"use client";

import { useQuery } from "@tanstack/react-query";
import { getSeaChest, type CredentialStatus } from "@/lib/seaChest";

export function useSeaChest() {
  return useQuery<CredentialStatus[]>({
    queryKey: ["sea-chest"],
    queryFn: () => getSeaChest(),
    staleTime: 30_000,
    retry: false,
  });
}
