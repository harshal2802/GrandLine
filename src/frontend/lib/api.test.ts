import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { apiFetch } from "@/lib/api";
import { useAuthStore } from "@/stores/auth";

describe("apiFetch (P4)", () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: "access-1", refreshToken: "refresh-1" });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    useAuthStore.getState().logout();
  });

  it("injects the bearer token from the store", async () => {
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );
    vi.stubGlobal("fetch", fetchMock);

    await apiFetch("/voyages");

    const init = fetchMock.mock.calls[0][1] as RequestInit;
    const headers = new Headers(init.headers);
    expect(headers.get("Authorization")).toBe("Bearer access-1");
  });

  it("refreshes and retries once on 401", async () => {
    const fetchMock = vi
      .fn()
      // first protected call → 401
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      // refresh call
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({ access_token: "access-2", refresh_token: "refresh-2" }),
          { status: 200 },
        ),
      )
      // retry → 200
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ ok: true }), { status: 200 }),
      );
    vi.stubGlobal("fetch", fetchMock);

    const result = await apiFetch<{ ok: boolean }>("/voyages");
    expect(result.ok).toBe(true);
    expect(useAuthStore.getState().accessToken).toBe("access-2");
  });

  it("redirects to /login when refresh fails", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(new Response("{}", { status: 401 }))
      .mockResolvedValueOnce(new Response("{}", { status: 401 })); // refresh fails
    vi.stubGlobal("fetch", fetchMock);

    const loc = { pathname: "/app/sea-chart", search: "", href: "" };
    vi.stubGlobal("window", { location: loc } as unknown as Window);

    await expect(apiFetch("/voyages")).rejects.toThrow();
    expect(loc.href).toContain("/login?redirect=");
  });
});
