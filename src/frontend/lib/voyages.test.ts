import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { createVoyage, startVoyage, MIN_TASK_LENGTH } from "@/lib/voyages";
import { useAuthStore } from "@/stores/auth";

describe("voyage lifecycle API", () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: "access-1", refreshToken: "refresh-1" });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.getState().logout();
  });

  it("POSTs /voyages with the create payload", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ id: "v1", title: "Find One Piece" }), {
        status: 201,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    const voyage = await createVoyage({
      title: "Find One Piece",
      description: "Sail the GrandLine",
    });

    expect(voyage.id).toBe("v1");
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/voyages");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({
      title: "Find One Piece",
      description: "Sail the GrandLine",
    });
  });

  it("POSTs /voyages/{id}/start with the task", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ voyage_id: "v1", status: "CHARTED" }), {
        status: 202,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await startVoyage("v1", "Build a URL shortener");

    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toContain("/voyages/v1/start");
    expect(JSON.parse(init.body as string)).toEqual({
      task: "Build a URL shortener",
      deploy_tier: "preview",
      approved_by: null,
    });
  });

  it("sends the chosen tier and approver when provided", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ voyage_id: "v2", status: "CHARTED" }), {
        status: 202,
      }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await startVoyage("v2", "Ship to production safely", {
      deployTier: "production",
      approvedBy: "user-123",
    });

    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(init.body as string)).toEqual({
      task: "Ship to production safely",
      deploy_tier: "production",
      approved_by: "user-123",
    });
  });

  it("exposes the backend's minimum task length", () => {
    expect(MIN_TASK_LENGTH).toBe(10);
  });
});
