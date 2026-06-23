import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor, cleanup } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { useBuildArtifacts } from "./useBuildArtifacts";
import type { BuildArtifact } from "@/lib/types";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

function artifact(over: Partial<BuildArtifact> = {}): BuildArtifact {
  return {
    id: "a1",
    voyage_id: "v1",
    shipwright_run_id: "r1",
    phase_number: 1,
    file_path: "src/main.py",
    content: "print('hi')",
    language: "python",
    created_by: "shipwright",
    created_at: "2026-06-22T00:00:00Z",
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

describe("useBuildArtifacts", () => {
  it("fetches the all-phases build-artifacts URL (no phase_number) and returns artifacts", async () => {
    const arts = [artifact(), artifact({ id: "a2", phase_number: 2 })];
    apiFetch.mockResolvedValue({
      voyage_id: "v1",
      phase_number: null,
      artifacts: arts,
    });

    const { result } = renderHook(() => useBuildArtifacts("v1"), {
      wrapper: wrapper(),
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiFetch).toHaveBeenCalledWith("/voyages/v1/build-artifacts");
    expect(result.current.data).toEqual(arts);
  });

  it("is disabled (does not fetch) when no voyageId is given", () => {
    const { result } = renderHook(() => useBuildArtifacts(null), {
      wrapper: wrapper(),
    });
    expect(apiFetch).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});
