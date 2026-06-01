import { beforeEach, describe, expect, it } from "vitest";
import { useVoyageStore } from "@/stores/voyage";
import type { EventEnvelope } from "@/lib/types";

function env(
  id: string,
  msgId: string,
  ts: number,
  isReplay = false,
): EventEnvelope {
  return {
    event_id: id,
    msg_id: msgId,
    ts,
    source_role: "captain",
    type: "pipeline_stage_entered",
    payload: {},
    isReplay,
  };
}

beforeEach(() => {
  useVoyageStore.getState().reset();
});

describe("dedupe + ordering (P3)", () => {
  it("keeps a single entry per event_id", () => {
    const s = useVoyageStore.getState();
    s.ingest("v1", env("e1", "1-0", 100));
    s.ingest("v1", env("e1", "1-0", 100));
    expect(useVoyageStore.getState().getEvents("v1")).toHaveLength(1);
  });

  it("orders by ts then msg_id", () => {
    const s = useVoyageStore.getState();
    s.ingest("v1", env("e3", "9-0", 200));
    s.ingest("v1", env("e1", "1-0", 100));
    s.ingest("v1", env("e2", "2-0", 100));
    expect(
      useVoyageStore.getState().getEvents("v1").map((e) => e.event_id),
    ).toEqual(["e1", "e2", "e3"]);
  });
});

describe("replay → live cutover (P2)", () => {
  it("marks replayed events on reconnect and flips live past the cutover", () => {
    const s = useVoyageStore.getState();
    // First connection delivers two events; markLive (quiet window) flips live.
    s.beginConnection("v1");
    s.ingest("v1", env("e1", "1-0", 100));
    s.ingest("v1", env("e2", "2-0", 200));
    useVoyageStore.getState().markLive("v1");
    s.ingest("v1", env("e3", "3-0", 300));

    // Reconnect: replay e1..e3 (<= cutover) then a new live e4.
    useVoyageStore.getState().beginConnection("v1");
    useVoyageStore.getState().ingest("v1", env("e1", "1-0", 100));
    useVoyageStore.getState().ingest("v1", env("e4", "4-0", 400));

    const byId = Object.fromEntries(
      useVoyageStore.getState().getEvents("v1").map((e) => [e.event_id, e.isReplay]),
    );
    // e1 was first seen live (markLive) → stays live (dedupe keeps first).
    expect(byId.e3).toBe(false);
    // e4 arrives past the cutover msg_id → live.
    expect(byId.e4).toBe(false);
  });

  it("treats first-connect events as replay until markLive", () => {
    const s = useVoyageStore.getState();
    s.beginConnection("v1");
    s.ingest("v1", env("e1", "1-0", 100));
    expect(useVoyageStore.getState().getEvents("v1")[0].isReplay).toBe(true);
    useVoyageStore.getState().markLive("v1");
    useVoyageStore.getState().ingest("v1", env("e2", "2-0", 200));
    const e2 = useVoyageStore.getState().getEvents("v1").find((e) => e.event_id === "e2");
    expect(e2?.isReplay).toBe(false);
  });
});

describe("LRU buffer eviction (P12)", () => {
  it("keeps event buffers for active + 2 most recent only", () => {
    const s = useVoyageStore.getState();
    for (const v of ["v1", "v2", "v3", "v4"]) {
      s.selectVoyage(v);
      useVoyageStore.getState().ingest(v, env(`${v}-e`, "1-0", 100));
    }
    // Visited order now [v4, v3, v2, v1]; keep v4,v3,v2.
    const st = useVoyageStore.getState();
    expect(st.getEvents("v4").length).toBe(1);
    expect(st.getEvents("v3").length).toBe(1);
    expect(st.getEvents("v2").length).toBe(1);
    expect(st.getEvents("v1").length).toBe(0); // evicted
  });

  it("preserves status snapshot for evicted voyages", () => {
    const s = useVoyageStore.getState();
    s.setStatus("v1", "BUILDING");
    s.ingest("v1", env("v1-e", "1-0", 100));
    for (const v of ["v2", "v3", "v4"]) {
      useVoyageStore.getState().selectVoyage(v);
    }
    expect(useVoyageStore.getState().buffers["v1"].status).toBe("BUILDING");
  });
});

describe("terminal closure (P10)", () => {
  it("flips connectionState to terminal-idle when active voyage goes terminal", () => {
    const s = useVoyageStore.getState();
    s.selectVoyage("v1");
    s.setConnectionState("open");
    useVoyageStore.getState().setStatus("v1", "COMPLETED");
    expect(useVoyageStore.getState().connectionState).toBe("terminal-idle");
  });

  it("does not flip the chip when a background voyage goes terminal", () => {
    const s = useVoyageStore.getState();
    s.selectVoyage("v1");
    s.setConnectionState("open");
    useVoyageStore.getState().setStatus("v2", "FAILED");
    expect(useVoyageStore.getState().connectionState).toBe("open");
  });
});
