import { describe, expect, it } from "vitest";
import { compareEnvelopes, normalizeFrame } from "@/lib/eventEnvelope";
import type { EventEnvelope, RawEventFrame } from "@/lib/types";

function frame(overrides: Partial<RawEventFrame["payload"]["event"]> = {}, msgId = "1-0"): RawEventFrame {
  return {
    type: "event",
    payload: {
      msg_id: msgId,
      event: {
        event_id: "e1",
        event_type: "pipeline_stage_entered",
        voyage_id: "v1",
        timestamp: "2026-04-01T00:00:00.000Z",
        source_role: "captain",
        payload: { stage: "PLANNING" },
        ...overrides,
      },
    },
  };
}

describe("normalizeFrame (P3)", () => {
  it("maps backend fields to the canonical envelope", () => {
    const env = normalizeFrame(frame(), false);
    expect(env.event_id).toBe("e1");
    expect(env.msg_id).toBe("1-0");
    expect(env.type).toBe("pipeline_stage_entered");
    expect(env.source_role).toBe("captain");
    expect(env.ts).toBe(Date.parse("2026-04-01T00:00:00.000Z"));
    expect(env.payload).toEqual({ stage: "PLANNING" });
    expect(env.isReplay).toBe(false);
  });

  it("snapshots isReplay at receipt", () => {
    expect(normalizeFrame(frame(), true).isReplay).toBe(true);
  });
});

describe("compareEnvelopes (P3)", () => {
  const mk = (ts: number, msg_id: string): EventEnvelope => ({
    event_id: msg_id,
    msg_id,
    ts,
    source_role: "captain",
    type: "x",
    payload: {},
    isReplay: false,
  });

  it("orders by ts then msg_id", () => {
    const list = [mk(2, "9-0"), mk(1, "2-0"), mk(1, "1-0")];
    const sorted = [...list].sort(compareEnvelopes).map((e) => e.msg_id);
    expect(sorted).toEqual(["1-0", "2-0", "9-0"]);
  });
});
