// Playback reducer (CONTRACTS P5). The ONLY path from raw events to playback
// state. Pure + deterministic so views can render state-as-of-cursor by
// reducing events with ts <= cursorTs. Only milestone-derivable state lives
// here — no past Poneglyph text, validation text, or deployment URL (P5).

import type { EventEnvelope, VoyageStatus } from "@/lib/types";

export type PhaseState = "PENDING" | "BUILDING" | "BUILT" | "FAILED";

export type PlaybackState = {
  status: VoyageStatus | null;
  phaseStatus: Record<number, PhaseState>;
  activeCrew: string | null;
  completedPhases: number[];
  failure: { stage: string; code: string; message: string } | null;
};

export function emptyPlaybackState(): PlaybackState {
  return {
    status: null,
    phaseStatus: {},
    activeCrew: null,
    completedPhases: [],
    failure: null,
  };
}

function phaseNum(e: EventEnvelope): number | null {
  const p = e.payload?.phase_number;
  return typeof p === "number" ? p : null;
}

// Reduce already-filtered events (ts <= cursor) into derived state. Events must
// be supplied in canonical (ts, msg_id) order.
export function reducePlayback(events: EventEnvelope[]): PlaybackState {
  const state = emptyPlaybackState();

  for (const e of events) {
    switch (e.type) {
      case "pipeline_stage_entered": {
        const stage = (e.payload.voyage_status ?? e.payload.stage) as VoyageStatus | undefined;
        if (stage) state.status = stage;
        state.activeCrew = e.source_role;
        break;
      }
      case "phase_build_started": {
        const n = phaseNum(e);
        if (n !== null) state.phaseStatus[n] = "BUILDING";
        state.activeCrew = e.source_role;
        break;
      }
      case "tests_passed": {
        const n = phaseNum(e);
        if (n !== null) {
          state.phaseStatus[n] = "BUILT";
          if (!state.completedPhases.includes(n)) state.completedPhases.push(n);
        }
        break;
      }
      case "phase_build_failed": {
        const n = phaseNum(e);
        if (n !== null) state.phaseStatus[n] = "FAILED";
        break;
      }
      case "pipeline_failed": {
        state.failure = {
          stage: (e.payload.stage as string) ?? "",
          code: (e.payload.code as string) ?? "",
          message: (e.payload.message as string) ?? "",
        };
        break;
      }
      case "pipeline_completed": {
        state.status = "COMPLETED";
        state.activeCrew = null;
        break;
      }
      default:
        break;
    }
  }

  state.completedPhases.sort((a, b) => a - b);
  return state;
}
