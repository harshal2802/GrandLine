import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { useClaudeLogin } from "./useClaudeLogin";

const startClaudeLogin = vi.fn();
const pollClaudeLogin = vi.fn();
vi.mock("@/lib/integrations", () => ({
  startClaudeLogin: (...a: unknown[]) => startClaudeLogin(...a),
  pollClaudeLogin: (...a: unknown[]) => pollClaudeLogin(...a),
}));

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  startClaudeLogin.mockReset();
  pollClaudeLogin.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("useClaudeLogin", () => {
  it("begin → awaiting (URL + login_id) → poll connected, invalidating sea-chest", async () => {
    startClaudeLogin.mockResolvedValue({
      verification_uri: "https://claude.ai/device",
      user_code: "WXYZ-1234",
      login_id: "lid-1",
    });
    pollClaudeLogin.mockResolvedValue({ status: "connected", label: "claude-login", error: null });

    const client = new QueryClient();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    const { result } = renderHook(() => useClaudeLogin(), { wrapper: wrapper(client) });

    expect(result.current.phase).toBe("idle");

    act(() => result.current.begin());

    await waitFor(() => expect(result.current.phase).toBe("connected"));
    expect(startClaudeLogin).toHaveBeenCalled();
    expect(pollClaudeLogin).toHaveBeenCalledWith("lid-1");
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["sea-chest"] });
  });

  it("surfaces a start failure as the error phase", async () => {
    startClaudeLogin.mockRejectedValue(new Error("Cabin runtime is not available"));

    const client = new QueryClient();
    const { result } = renderHook(() => useClaudeLogin(), { wrapper: wrapper(client) });

    act(() => result.current.begin());

    await waitFor(() => expect(result.current.phase).toBe("error"));
    expect(result.current.error).toMatch(/Cabin runtime is not available/);
  });

  it("maps a poll error status to the error phase", async () => {
    startClaudeLogin.mockResolvedValue({
      verification_uri: "https://claude.ai/device",
      user_code: null,
      login_id: "lid-2",
    });
    pollClaudeLogin.mockResolvedValue({ status: "error", label: null, error: "login_timeout" });

    const client = new QueryClient();
    const { result } = renderHook(() => useClaudeLogin(), { wrapper: wrapper(client) });

    act(() => result.current.begin());

    await waitFor(() => expect(result.current.phase).toBe("error"));
    expect(result.current.error).toBe("login_timeout");
  });

  it("reset returns to idle", async () => {
    startClaudeLogin.mockResolvedValue({
      verification_uri: "https://claude.ai/device",
      user_code: null,
      login_id: "lid-3",
    });
    pollClaudeLogin.mockResolvedValue({ status: "pending", label: null, error: null });

    const client = new QueryClient();
    const { result } = renderHook(() => useClaudeLogin(), { wrapper: wrapper(client) });

    act(() => result.current.begin());
    await waitFor(() => expect(result.current.phase).toBe("awaiting"));

    act(() => result.current.reset());
    expect(result.current.phase).toBe("idle");
    expect(result.current.start).toBeNull();
  });
});
