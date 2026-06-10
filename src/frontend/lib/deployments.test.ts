import { describe, expect, it } from "vitest";
import { latestDeployment } from "@/lib/deployments";
import type { EventEnvelope } from "@/lib/types";

function ev(type: string, payload: Record<string, unknown>, msg = "1"): EventEnvelope {
  return {
    event_id: `e-${msg}`,
    msg_id: msg,
    ts: Number(msg),
    source_role: "helmsman",
    type,
    payload,
    isReplay: false,
  };
}

describe("latestDeployment", () => {
  it("returns null when there is no deployment_completed event", () => {
    expect(latestDeployment([])).toBeNull();
    expect(latestDeployment([ev("phase_build_started", { phase_number: 1 })])).toBeNull();
  });

  it("reads url and tier from a deployment_completed event", () => {
    const d = latestDeployment([
      ev("deployment_completed", { url: "https://preview.example.com", tier: "preview" }),
    ]);
    expect(d).toEqual({ url: "https://preview.example.com", tier: "preview" });
  });

  it("returns the latest deployment when several exist", () => {
    const d = latestDeployment([
      ev("deployment_completed", { url: "https://staging.example.com", tier: "staging" }, "1"),
      ev("deployment_completed", { url: "https://prod.example.com", tier: "production" }, "2"),
    ]);
    expect(d).toEqual({ url: "https://prod.example.com", tier: "production" });
  });

  it("tolerates a missing url", () => {
    const d = latestDeployment([ev("deployment_completed", { tier: "preview" })]);
    expect(d).toEqual({ url: null, tier: "preview" });
  });
});
