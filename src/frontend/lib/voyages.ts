// Voyage lifecycle API calls: chart a course (POST /voyages) and set sail
// (POST /voyages/{id}/start). All go through apiFetch so auth refresh (P4)
// is handled.

import { apiFetch } from "@/lib/api";
import type { DeployTier, VoyageListItem } from "@/lib/types";

export type VoyageCreatePayload = {
  title: string;
  description?: string | null;
  target_repo?: string | null;
};

// Backend validation: StartVoyageRequest.task requires >= 10 chars.
export const MIN_TASK_LENGTH = 10;

export function createVoyage(payload: VoyageCreatePayload) {
  return apiFetch<VoyageListItem>("/voyages", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export type StartVoyageOptions = {
  deployTier?: DeployTier;
  // The approving user's id; required by the backend when deployTier is
  // "production" (the Helmsman refuses to sail to production unapproved).
  approvedBy?: string | null;
};

export function startVoyage(id: string, task: string, opts: StartVoyageOptions = {}) {
  const deployTier = opts.deployTier ?? "preview";
  return apiFetch<{ voyage_id: string; status: string }>(`/voyages/${id}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      task,
      deploy_tier: deployTier,
      approved_by: opts.approvedBy ?? null,
    }),
  });
}
