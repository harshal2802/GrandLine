import { describe, expect, it } from "vitest";
import { reducePlayback } from "@/lib/playback/reducer";
import type { EventEnvelope } from "@/lib/types";

let seq = 0;
function ev(type: string, payload: Record<string, unknown>, role = "captain"): EventEnvelope {
  seq += 1;
  return {
    event_id: `e${seq}`,
    msg_id: `${seq}-0`,
    ts: seq * 1000,
    source_role: role as EventEnvelope["source_role"],
    type,
    payload,
    isReplay: false,
  };
}

describe("reducePlayback (P5)", () => {
  it("derives status + active crew from stage transitions", () => {
    const state = reducePlayback([
      ev("pipeline_stage_entered", { voyage_status: "PLANNING" }, "captain"),
      ev("pipeline_stage_entered", { voyage_status: "BUILDING" }, "shipwright"),
    ]);
    expect(state.status).toBe("BUILDING");
    expect(state.activeCrew).toBe("shipwright");
  });

  it("build_started → tests_passed yields BUILT + completed", () => {
    const state = reducePlayback([
      ev("phase_build_started", { phase_number: 2 }, "shipwright"),
      ev("tests_passed", { phase_number: 2 }, "shipwright"),
    ]);
    expect(state.phaseStatus[2]).toBe("BUILT");
    expect(state.completedPhases).toEqual([2]);
  });

  it("build_started → build_failed yields FAILED", () => {
    const state = reducePlayback([
      ev("phase_build_started", { phase_number: 3 }, "shipwright"),
      ev("phase_build_failed", { phase_number: 3, code: "TESTS", message: "boom" }, "shipwright"),
    ]);
    expect(state.phaseStatus[3]).toBe("FAILED");
  });

  it("rewind before any build → empty phase status", () => {
    expect(reducePlayback([]).phaseStatus).toEqual({});
  });

  it("captures pipeline failure", () => {
    const state = reducePlayback([
      ev("pipeline_failed", { stage: "BUILDING", code: "X", message: "kaboom" }),
    ]);
    expect(state.failure).toEqual({ stage: "BUILDING", code: "X", message: "kaboom" });
  });

  it("is deterministic / pure (same input → same output)", () => {
    const events = [ev("phase_build_started", { phase_number: 1 })];
    expect(reducePlayback(events)).toEqual(reducePlayback(events));
  });
});
