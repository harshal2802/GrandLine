// Intervention API calls (Phase 17). Thin wrappers over the pipeline control
// endpoints; all go through apiFetch so auth refresh (P4) is handled.

import { apiFetch } from "@/lib/api";

export function pauseVoyage(id: string) {
  return apiFetch(`/voyages/${id}/pause`, { method: "POST" });
}

export function resumeVoyage(id: string) {
  // `task` is required by validation but unused on resume (the plan already
  // exists); a >=10-char placeholder satisfies the schema.
  return apiFetch(`/voyages/${id}/resume`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ task: "resume-voyage", deploy_tier: "preview" }),
  });
}

export function cancelVoyage(id: string) {
  return apiFetch(`/voyages/${id}/cancel`, { method: "POST" });
}

export function injectContext(id: string, context: string, phaseNumber?: number) {
  return apiFetch(`/voyages/${id}/inject`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ context, phase_number: phaseNumber ?? null }),
  });
}

export function redirectPhase(id: string, phaseNumber: number, instruction: string) {
  return apiFetch(`/voyages/${id}/redirect`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ phase_number: phaseNumber, instruction }),
  });
}
