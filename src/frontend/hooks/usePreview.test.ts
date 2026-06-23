import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, renderHook, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { ApiError } from "@/lib/api";
import { usePreview, useStartPreview, useStopPreview } from "./usePreview";

const getPreview = vi.fn();
const startPreview = vi.fn();
const stopPreview = vi.fn();
vi.mock("@/lib/preview", () => ({
  getPreview: (...a: unknown[]) => getPreview(...a),
  startPreview: (...a: unknown[]) => startPreview(...a),
  stopPreview: (...a: unknown[]) => stopPreview(...a),
}));

function wrapper(client: QueryClient) {
  return ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
}

const info = { preview_id: "preview-1", url: "http://127.0.0.1:3000", status: "running" };

beforeEach(() => {
  getPreview.mockReset();
  startPreview.mockReset();
  stopPreview.mockReset();
});

afterEach(() => {
  cleanup();
});

describe("usePreview", () => {
  it("returns the running preview", async () => {
    getPreview.mockResolvedValue(info);
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => usePreview("v1"), { wrapper: wrapper(client) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(getPreview).toHaveBeenCalledWith("v1");
    expect(result.current.data).toEqual(info);
  });

  it("maps a 404 to null (no preview running, not an error)", async () => {
    getPreview.mockRejectedValue(new ApiError(404, "No preview running", "NOT_FOUND"));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => usePreview("v1"), { wrapper: wrapper(client) });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(result.current.data).toBeNull();
    expect(result.current.isError).toBe(false);
  });

  it("surfaces a non-404 error", async () => {
    getPreview.mockRejectedValue(new ApiError(503, "Cabin unavailable", "CABIN_UNAVAILABLE"));
    const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const { result } = renderHook(() => usePreview("v1"), { wrapper: wrapper(client) });

    await waitFor(() => expect(result.current.isError).toBe(true));
  });

  it("is idle without a voyageId", () => {
    const client = new QueryClient();
    const { result } = renderHook(() => usePreview(null), { wrapper: wrapper(client) });
    expect(getPreview).not.toHaveBeenCalled();
    expect(result.current.fetchStatus).toBe("idle");
  });
});

describe("useStartPreview / useStopPreview", () => {
  it("start sets the preview into the cache", async () => {
    startPreview.mockResolvedValue(info);
    const client = new QueryClient();
    const { result } = renderHook(() => useStartPreview("v1"), { wrapper: wrapper(client) });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(startPreview).toHaveBeenCalledWith("v1");
    expect(client.getQueryData(["preview", "v1"])).toEqual(info);
  });

  it("stop clears the preview from the cache", async () => {
    stopPreview.mockResolvedValue(undefined);
    const client = new QueryClient();
    client.setQueryData(["preview", "v1"], info);
    const { result } = renderHook(() => useStopPreview("v1"), { wrapper: wrapper(client) });

    await act(async () => {
      await result.current.mutateAsync();
    });

    expect(stopPreview).toHaveBeenCalledWith("v1");
    expect(client.getQueryData(["preview", "v1"])).toBeNull();
  });
});
