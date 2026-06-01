import { describe, expect, it } from "vitest";
import {
  applyFilters,
  EMPTY_FILTERS,
  mergeLog,
  rowFromCrewAction,
  rowFromEvent,
  type LogRow,
} from "@/lib/shipsLog";
import type { CrewActionRead, EventEnvelope } from "@/lib/types";

function rest(over: Partial<CrewActionRead> = {}): CrewActionRead {
  return {
    id: "a1",
    voyage_id: "v1",
    crew_member: "shipwright",
    action_type: "phase_build_completed",
    summary: "Built phase 2",
    details: { event_id: "ev-1", phase_number: 2 },
    created_at: "2026-04-01T00:00:02.000Z",
    ...over,
  };
}

function liveEvent(over: Partial<EventEnvelope> = {}): EventEnvelope {
  return {
    event_id: "ev-9",
    msg_id: "9-0",
    ts: Date.parse("2026-04-01T00:00:09.000Z"),
    source_role: "doctor",
    type: "crew_action_recorded",
    payload: {
      crew_action_id: "a9",
      event_id: "ev-9",
      action_type: "validation_passed",
      summary: "Validation passed",
      created_at: "2026-04-01T00:00:09.000Z",
      details: { phase_number: 2 },
    },
    isReplay: false,
    ...over,
  };
}

describe("rowFromEvent (P3)", () => {
  it("ignores non crew_action_recorded events", () => {
    expect(rowFromEvent(liveEvent({ type: "tests_passed" }))).toBeNull();
  });
  it("extracts the canonical row from a live event", () => {
    const row = rowFromEvent(liveEvent())!;
    expect(row.event_id).toBe("ev-9");
    expect(row.actionType).toBe("validation_passed");
    expect(row.phaseNumber).toBe(2);
  });
});

describe("mergeLog (P3, P13)", () => {
  it("dedupes by event_id with REST canonical", () => {
    const restRow = rowFromCrewAction(rest({ id: "a1", details: { event_id: "dup" } }));
    const liveRow = rowFromEvent(liveEvent({ event_id: "dup", payload: { ...liveEvent().payload, event_id: "dup" } }))!;
    const merged = mergeLog([restRow], [liveRow]);
    expect(merged).toHaveLength(1);
    expect(merged[0].id).toBe("a1"); // REST won
  });

  it("sorts newest-first by created_at", () => {
    const older = rowFromCrewAction(rest({ id: "a1", created_at: "2026-04-01T00:00:02.000Z", details: { event_id: "e2" } }));
    const newer = rowFromEvent(liveEvent())!;
    expect(mergeLog([older], [newer]).map((r) => r.event_id)).toEqual(["ev-9", "e2"]);
  });

  it("tie-breaks equal timestamps by id desc", () => {
    const ts = "2026-04-01T00:00:05.000Z";
    const a: LogRow = { ...rowFromCrewAction(rest({ id: "a", created_at: ts, details: { event_id: "a" } })) };
    const b: LogRow = { ...rowFromCrewAction(rest({ id: "b", created_at: ts, details: { event_id: "b" } })) };
    expect(mergeLog([a, b], []).map((r) => r.id)).toEqual(["b", "a"]);
  });
});

describe("applyFilters", () => {
  const rows = [
    rowFromCrewAction(rest({ id: "1", crew_member: "doctor", action_type: "validation_failed", summary: "boom", details: { event_id: "1", phase_number: 1 } })),
    rowFromCrewAction(rest({ id: "2", crew_member: "shipwright", action_type: "phase_build_completed", summary: "ok", details: { event_id: "2", phase_number: 2 } })),
  ];

  it("filters by crew role", () => {
    expect(applyFilters(rows, { ...EMPTY_FILTERS, crewRoles: ["doctor"] })).toHaveLength(1);
  });
  it("filters failure-only", () => {
    expect(applyFilters(rows, { ...EMPTY_FILTERS, failureOnly: true })[0].id).toBe("1");
  });
  it("filters by phase", () => {
    expect(applyFilters(rows, { ...EMPTY_FILTERS, phase: 2 })[0].id).toBe("2");
  });
  it("searches summary text", () => {
    expect(applyFilters(rows, { ...EMPTY_FILTERS, search: "boom" })[0].id).toBe("1");
  });
});
