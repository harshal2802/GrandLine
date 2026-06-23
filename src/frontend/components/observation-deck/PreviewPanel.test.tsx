import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { PreviewPanel } from "./PreviewPanel";
import type { PreviewInfo } from "@/lib/preview";

// Active voyage comes from the store; drive it directly.
let activeVoyageId: string | null = "v1";
vi.mock("@/stores/voyage", () => ({
  useVoyageStore: (selector: (s: { activeVoyageId: string | null }) => unknown) =>
    selector({ activeVoyageId }),
}));

// Controllable preview hooks.
const previewResult = {
  data: null as PreviewInfo | null,
  isLoading: false,
  isError: false,
};
const startMutation = { mutate: vi.fn(), isPending: false, isError: false, error: null as Error | null };
const stopMutation = { mutate: vi.fn(), isPending: false, isError: false, error: null as Error | null };
vi.mock("@/hooks/usePreview", () => ({
  usePreview: () => previewResult,
  useStartPreview: () => startMutation,
  useStopPreview: () => stopMutation,
}));

const logsResult = {
  lines: [] as string[],
  connection: "open",
  follow: true,
  setFollow: vi.fn(),
  clear: vi.fn(),
};
vi.mock("@/hooks/usePreviewLogs", () => ({
  usePreviewLogs: () => logsResult,
}));

function running(over: Partial<PreviewInfo> = {}): PreviewInfo {
  return { preview_id: "preview-1", url: "http://127.0.0.1:3000", status: "running", ...over };
}

beforeEach(() => {
  activeVoyageId = "v1";
  previewResult.data = null;
  previewResult.isLoading = false;
  previewResult.isError = false;
  startMutation.mutate = vi.fn();
  startMutation.isPending = false;
  startMutation.isError = false;
  startMutation.error = null;
  stopMutation.mutate = vi.fn();
  stopMutation.isPending = false;
  logsResult.lines = [];
});

afterEach(() => {
  cleanup();
});

describe("PreviewPanel", () => {
  it("prompts to select a voyage when none is active", () => {
    activeVoyageId = null;
    render(<PreviewPanel />);
    expect(screen.getByText(/select a voyage/i)).toBeInTheDocument();
  });

  it("shows a Start button + empty state when no preview is running", () => {
    render(<PreviewPanel />);
    const start = screen.getByRole("button", { name: /start preview/i });
    expect(start).toBeInTheDocument();
    expect(screen.getByText(/no preview is running/i)).toBeInTheDocument();

    fireEvent.click(start);
    expect(startMutation.mutate).toHaveBeenCalled();
  });

  it("renders the sandboxed iframe + logs + Stop when running", () => {
    previewResult.data = running();
    logsResult.lines = ["server started", "listening on :3000"];
    render(<PreviewPanel />);

    const iframe = screen.getByTitle("App preview");
    expect(iframe).toHaveAttribute("src", "http://127.0.0.1:3000");
    expect(iframe).toHaveAttribute(
      "sandbox",
      "allow-scripts allow-same-origin allow-forms allow-popups",
    );
    expect(screen.getByRole("link", { name: /open in new tab/i })).toHaveAttribute(
      "href",
      "http://127.0.0.1:3000",
    );
    expect(screen.getByText("server started")).toBeInTheDocument();

    const stop = screen.getByRole("button", { name: /stop preview/i });
    fireEvent.click(stop);
    expect(stopMutation.mutate).toHaveBeenCalled();
  });

  it("toggles follow/pause on the logs pane", () => {
    previewResult.data = running();
    render(<PreviewPanel />);
    fireEvent.click(screen.getByRole("button", { name: /pause/i }));
    expect(logsResult.setFollow).toHaveBeenCalledWith(false);
  });

  it("shows an error when start fails", () => {
    startMutation.isError = true;
    startMutation.error = new Error("Cabin unavailable");
    render(<PreviewPanel />);
    expect(screen.getByText(/cabin unavailable/i)).toBeInTheDocument();
  });

  it("shows a loading state", () => {
    previewResult.isLoading = true;
    render(<PreviewPanel />);
    expect(screen.getByText(/loading preview/i)).toBeInTheDocument();
  });
});
