import { describe, expect, it } from "vitest";
import { columnFor, columnForVoyage } from "./SeaChart";

const ACTIVE = "v-active";

describe("columnFor", () => {
  it("maps stages to their columns", () => {
    expect(columnFor("PDD")).toBe("pdd");
    expect(columnFor("TDD")).toBe("tdd");
    expect(columnFor("BUILDING")).toBe("building");
    expect(columnFor("CHARTED")).toBe("planning");
  });
});

describe("columnForVoyage (PAUSED placement)", () => {
  it("keeps the active paused voyage in its pre-pause stage column", () => {
    const v = { id: ACTIVE, status: "PAUSED" as const };
    // Paused during PDD → stays in the PDD column, not Building.
    expect(columnForVoyage(v, ACTIVE, "PDD")).toBe("pdd");
    expect(columnForVoyage(v, ACTIVE, "TDD")).toBe("tdd");
  });

  it("falls back to the polled status when there is no live stage", () => {
    const v = { id: ACTIVE, status: "PAUSED" as const };
    // No reducer status (e.g. non-active or no events) → Building fallback.
    expect(columnForVoyage(v, ACTIVE, null)).toBe("building");
  });

  it("does not override a non-active paused voyage", () => {
    const v = { id: "v-other", status: "PAUSED" as const };
    expect(columnForVoyage(v, ACTIVE, "PDD")).toBe("building");
  });

  it("ignores the live status for a non-paused voyage", () => {
    const v = { id: ACTIVE, status: "BUILDING" as const };
    expect(columnForVoyage(v, ACTIVE, "PDD")).toBe("building");
  });
});
