// Derived progress selector (Decision 8). Pure functions over a voyage's
// phase_status map + status, so views read a single shape instead of
// re-deriving. Playback (Phase 5) feeds reduced phase_status here too.

import type { VoyageListItem, VoyageStatus } from "@/lib/types";

export type VoyageProgress = {
  phasesBuilt: number;
  totalPhases: number;
  percentComplete: number;
  currentStage: VoyageStatus;
  failure: boolean;
};

const BUILT = new Set(["BUILT", "COMPLETED", "PASSED"]);

export function computeProgress(
  status: VoyageStatus,
  phaseStatus: Record<string, string> | undefined,
): VoyageProgress {
  const entries = Object.entries(phaseStatus ?? {});
  const total = entries.length;
  const built = entries.filter(([, s]) => BUILT.has(s.toUpperCase())).length;
  const pct = total === 0 ? (status === "COMPLETED" ? 100 : 0) : Math.round((built / total) * 100);
  return {
    phasesBuilt: built,
    totalPhases: total,
    percentComplete: pct,
    currentStage: status,
    failure: status === "FAILED" || entries.some(([, s]) => s.toUpperCase() === "FAILED"),
  };
}

export function useVoyageProgress(voyage: VoyageListItem): VoyageProgress {
  return computeProgress(voyage.status, voyage.phase_status);
}
