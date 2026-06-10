// Deployment API calls (Helmsman) + a helper to read the latest deployment off
// the event stream. The deployment URL is intentionally NOT carried in the
// playback reducer (P5 keeps only milestone-derivable state), so views derive
// it directly from `deployment_completed` events here.

import { apiFetch } from "@/lib/api";
import type { DeployTier, EventEnvelope } from "@/lib/types";

export type Deployment = {
  url: string | null;
  tier: DeployTier | null;
};

// Roll back the latest deployment for a tier (POST /voyages/{id}/rollback).
export function rollbackDeployment(voyageId: string, tier: DeployTier) {
  return apiFetch(`/voyages/${voyageId}/rollback`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tier }),
  });
}

// Most recent successful deployment from a voyage's events, or null. Scans from
// the end so the latest `deployment_completed` wins.
export function latestDeployment(events: EventEnvelope[]): Deployment | null {
  for (let i = events.length - 1; i >= 0; i--) {
    if (events[i].type === "deployment_completed") {
      const payload = events[i].payload;
      const url = typeof payload.url === "string" ? payload.url : null;
      const tier =
        typeof payload.tier === "string" ? (payload.tier as DeployTier) : null;
      return { url, tier };
    }
  }
  return null;
}
