import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor, cleanup } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import {
  pickHeadBranch,
  useChangedFiles,
  useFileDiff,
  useGitHead,
} from "./useGitDiff";

const apiFetch = vi.fn();
vi.mock("@/lib/api", () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
}));

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

describe("pickHeadBranch", () => {
  it("prefers the agent/* branch", () => {
    expect(
      pickHeadBranch([
        { name: "main", is_current: false },
        { name: "agent/shipwright/abc12345", is_current: true },
      ]),
    ).toBe("agent/shipwright/abc12345");
  });

  it("falls back to the current non-base branch", () => {
    expect(
      pickHeadBranch([
        { name: "main", is_current: false },
        { name: "feat/x", is_current: true },
      ]),
    ).toBe("feat/x");
  });

  it("returns null when only the base branch exists", () => {
    expect(pickHeadBranch([{ name: "main", is_current: true }])).toBeNull();
  });
});

describe("useGitHead", () => {
  it("resolves the crew branch from /git/branches", async () => {
    apiFetch.mockResolvedValue([
      { name: "main", is_current: false },
      { name: "agent/shipwright/abc12345", is_current: true },
    ]);

    const { result } = renderHook(() => useGitHead("v1"), { wrapper: wrapper() });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiFetch).toHaveBeenCalledWith("/voyages/v1/git/branches");
    expect(result.current.data).toBe("agent/shipwright/abc12345");
  });

  it("is idle with no voyageId", () => {
    const { result } = renderHook(() => useGitHead(null), { wrapper: wrapper() });
    expect(apiFetch).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useChangedFiles", () => {
  it("fetches the changed-files URL with base + head and returns the list", async () => {
    const files = [{ path: "src/main.py", status: "M" }];
    apiFetch.mockResolvedValue(files);

    const { result } = renderHook(
      () => useChangedFiles("v1", "agent/shipwright/abc12345"),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiFetch).toHaveBeenCalledWith(
      "/voyages/v1/git/changed-files?base=main&head=agent%2Fshipwright%2Fabc12345",
    );
    expect(result.current.data).toEqual(files);
  });

  it("is idle without a head branch", () => {
    const { result } = renderHook(() => useChangedFiles("v1", null), {
      wrapper: wrapper(),
    });
    expect(apiFetch).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useFileDiff", () => {
  it("includes the path query param when a file is selected", async () => {
    apiFetch.mockResolvedValue({
      base: "main",
      head: "agent/x",
      path: "src/main.py",
      unified: "diff",
    });

    const { result } = renderHook(
      () => useFileDiff("v1", "agent/x", "src/main.py"),
      { wrapper: wrapper() },
    );

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(apiFetch).toHaveBeenCalledWith(
      "/voyages/v1/git/diff?base=main&head=agent%2Fx&path=src%2Fmain.py",
    );
  });

  it("is idle without a head branch", () => {
    const { result } = renderHook(() => useFileDiff("v1", null, null), {
      wrapper: wrapper(),
    });
    expect(apiFetch).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});
