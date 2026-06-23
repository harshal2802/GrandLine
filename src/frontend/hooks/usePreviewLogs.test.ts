import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, renderHook, waitFor, act } from "@testing-library/react";
import { usePreviewLogs } from "./usePreviewLogs";

vi.mock("@/lib/auth/cookie", () => ({ readCookie: () => "cookie-token" }));
vi.mock("@/stores/auth", () => ({
  useAuthStore: { getState: () => ({ accessToken: "store-token" }) },
}));

// Build a Response whose body streams the given SSE chunks then ends.
function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let i = 0;
  const body = {
    getReader() {
      return {
        read() {
          if (i < chunks.length) {
            const value = encoder.encode(chunks[i]);
            i += 1;
            return Promise.resolve({ done: false, value });
          }
          return Promise.resolve({ done: true, value: undefined });
        },
      };
    },
  };
  return { ok: true, body } as unknown as Response;
}

beforeEach(() => {
  vi.stubGlobal("fetch", vi.fn());
});

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("usePreviewLogs", () => {
  it("does not connect when disabled", () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    const { result } = renderHook(() => usePreviewLogs("v1", false));
    expect(fetchMock).not.toHaveBeenCalled();
    expect(result.current.connection).toBe("idle");
  });

  it("streams data: lines into the buffer with the bearer token", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(
      sseResponse(["data: line one\n\n", "data: line two\n\n"]),
    );

    const { result } = renderHook(() => usePreviewLogs("v1", true));

    await waitFor(() => expect(result.current.lines).toEqual(["line one", "line two"]));

    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toContain("/voyages/v1/preview/logs/stream");
    expect((init.headers as Record<string, string>).Authorization).toBe("Bearer store-token");
    await waitFor(() => expect(result.current.connection).toBe("closed"));
  });

  it("toggles follow and clears the buffer", async () => {
    const fetchMock = fetch as unknown as ReturnType<typeof vi.fn>;
    fetchMock.mockResolvedValue(sseResponse(["data: x\n\n"]));

    const { result } = renderHook(() => usePreviewLogs("v1", true));
    await waitFor(() => expect(result.current.lines).toEqual(["x"]));

    expect(result.current.follow).toBe(true);
    act(() => result.current.setFollow(false));
    expect(result.current.follow).toBe(false);

    act(() => result.current.clear());
    expect(result.current.lines).toEqual([]);
  });
});
