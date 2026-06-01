import { describe, expect, it } from "vitest";
import { computeProgress } from "@/hooks/useVoyageProgress";

describe("computeProgress (Decision 8)", () => {
  it("counts built phases and derives percent", () => {
    const p = computeProgress("BUILDING", { "1": "BUILT", "2": "BUILDING", "3": "PENDING", "4": "BUILT" });
    expect(p.phasesBuilt).toBe(2);
    expect(p.totalPhases).toBe(4);
    expect(p.percentComplete).toBe(50);
    expect(p.failure).toBe(false);
  });

  it("flags failure from status or phase state", () => {
    expect(computeProgress("FAILED", {}).failure).toBe(true);
    expect(computeProgress("BUILDING", { "1": "FAILED" }).failure).toBe(true);
  });

  it("treats a completed voyage with no phases as 100%", () => {
    expect(computeProgress("COMPLETED", {}).percentComplete).toBe(100);
  });

  it("is a pure function (no mutation of input)", () => {
    const input = { "1": "BUILT" };
    computeProgress("BUILDING", input);
    expect(input).toEqual({ "1": "BUILT" });
  });
});
