import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { useAuthStore } from "@/stores/auth";

function jwt(claims: Record<string, unknown>): string {
  const b64 = (o: unknown) => Buffer.from(JSON.stringify(o)).toString("base64url");
  return `${b64({ alg: "HS256" })}.${b64(claims)}.sig`;
}

describe("auth store", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    useAuthStore.getState().logout();
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  it("login populates tokens + user and schedules refresh (P4)", async () => {
    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(
        new Response(
          JSON.stringify({
            access_token: jwt({ exp: Date.now() / 1000 + 1800 }),
            refresh_token: "r1",
          }),
          { status: 200 },
        ),
      )
      .mockResolvedValueOnce(
        new Response(JSON.stringify({ id: "u1", email: "a@b.c", username: "cap" }), {
          status: 200,
        }),
      );
    vi.stubGlobal("fetch", fetchMock);

    await useAuthStore.getState().login("a@b.c", "pw");

    expect(useAuthStore.getState().refreshToken).toBe("r1");
    expect(useAuthStore.getState().user?.username).toBe("cap");
    expect(useAuthStore.getState().refreshTimer).not.toBeNull();
  });

  it("logout clears everything", () => {
    useAuthStore.setState({ accessToken: "a", refreshToken: "r" });
    useAuthStore.getState().logout();
    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().refreshToken).toBeNull();
  });

  it("pre-emptive refresh fires ~60s before exp (P4)", async () => {
    // Token expires in 90s → refresh scheduled at 30s.
    const access = jwt({ exp: Date.now() / 1000 + 90 });
    const fetchMock = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({ access_token: jwt({ exp: Date.now() / 1000 + 1800 }), refresh_token: "r2" }),
        { status: 200 },
      ),
    );
    vi.stubGlobal("fetch", fetchMock);

    useAuthStore.getState().setTokens({
      access_token: access,
      refresh_token: "r1",
      token_type: "bearer",
    });

    // Nothing yet.
    expect(fetchMock).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(31_000);
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/auth/refresh"),
      expect.anything(),
    );
  });
});
