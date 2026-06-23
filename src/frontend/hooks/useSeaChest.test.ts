import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor, cleanup } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { useSeaChest } from "./useSeaChest";
import type { CredentialStatus } from "@/lib/seaChest";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

function status(over: Partial<CredentialStatus> = {}): CredentialStatus {
  return {
    kind: "claude_code",
    connected: true,
    label: "device-login",
    created_at: "2026-06-22T00:00:00Z",
    last_used_at: null,
    ...over,
  };
}

function wrapper() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

beforeEach(() => {
  apiFetch.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("useSeaChest", () => {
  it("reads GET /sea-chest and returns the credential statuses", async () => {
    const statuses = [
      status(),
      status({ kind: "github", connected: false, label: null }),
    ];
    apiFetch.mockResolvedValue(statuses);

    const { result } = renderHook(() => useSeaChest(), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiFetch).toHaveBeenCalledWith("/sea-chest");
    expect(result.current.data).toEqual(statuses);
  });
});
