// Voyage lifecycle API calls: chart a course (POST /voyages) and set sail
// (POST /voyages/{id}/start). All go through apiFetch so auth refresh (P4)
// is handled.

import { apiFetch } from "@/lib/api";
import type { VoyageListItem } from "@/lib/types";

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

export function startVoyage(id: string, task: string) {
  return apiFetch<{ voyage_id: string; status: string }>(`/voyages/${id}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task, deploy_tier: "preview" }),
  });
}
