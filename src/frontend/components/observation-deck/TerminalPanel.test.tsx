import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, render, screen } from "@testing-library/react";

// --- Mock xterm + addon-fit (no real terminal / DOM canvas in jsdom). ---------
const onDataHandlers: Array<(data: string) => void> = [];
const onResizeHandlers: Array<() => void> = [];
const termInstance = {
  cols: 80,
  rows: 24,
  loadAddon: vi.fn(),
  open: vi.fn(),
  write: vi.fn(),
  dispose: vi.fn(),
  onData: vi.fn((cb: (data: string) => void) => {
    onDataHandlers.push(cb);
    return { dispose: vi.fn() };
  }),
  onResize: vi.fn((cb: () => void) => {
    onResizeHandlers.push(cb);
    return { dispose: vi.fn() };
  }),
};
const fitInstance = { fit: vi.fn() };

vi.mock("@xterm/xterm", () => ({
  Terminal: vi.fn(() => termInstance),
}));
vi.mock("@xterm/addon-fit", () => ({
  FitAddon: vi.fn(() => fitInstance),
}));
vi.mock("@xterm/xterm/css/xterm.css", () => ({}));

// --- Mock the WS lifecycle hook so we can drive output + assert senders. ------
let capturedOnOutput: (data: string) => void = () => {};
let capturedEnabled = false;
const sendInput = vi.fn();
const sendResize = vi.fn();
let connection = "open";
vi.mock("@/hooks/useCabinTerminal", () => ({
  useCabinTerminal: (opts: {
    voyageId: string | null;
    enabled: boolean;
    onOutput: (data: string) => void;
  }) => {
    capturedOnOutput = opts.onOutput;
    capturedEnabled = opts.enabled;
    return { connection, sendInput, sendResize };
  },
}));

// ResizeObserver isn't in jsdom — provide a no-op.
class FakeResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}
vi.stubGlobal("ResizeObserver", FakeResizeObserver);

import { TerminalPanel } from "./TerminalPanel";

beforeEach(() => {
  onDataHandlers.length = 0;
  onResizeHandlers.length = 0;
  sendInput.mockReset();
  sendResize.mockReset();
  termInstance.write.mockReset();
  termInstance.dispose.mockReset();
  termInstance.open.mockReset();
  connection = "open";
});

afterEach(() => {
  cleanup();
});

describe("TerminalPanel", () => {
  it("prompts to select a voyage when none is active", () => {
    render(<TerminalPanel voyageId={null} />);
    expect(screen.getByText(/select a voyage/i)).toBeInTheDocument();
    expect(capturedEnabled).toBe(false);
  });

  it("mounts an xterm terminal and opens it on the container", () => {
    render(<TerminalPanel voyageId="v1" />);
    expect(termInstance.open).toHaveBeenCalledTimes(1);
    expect(screen.getByTestId("terminal-surface")).toBeInTheDocument();
  });

  it("writes WS output to the terminal", () => {
    render(<TerminalPanel voyageId="v1" />);
    capturedOnOutput("hello from the cabin");
    expect(termInstance.write).toHaveBeenCalledWith("hello from the cabin");
  });

  it("forwards terminal input to the WS", () => {
    render(<TerminalPanel voyageId="v1" />);
    onDataHandlers.forEach((cb) => cb("ls\n"));
    expect(sendInput).toHaveBeenCalledWith("ls\n");
  });

  it("forwards a resize to the WS", () => {
    render(<TerminalPanel voyageId="v1" />);
    onResizeHandlers.forEach((cb) => cb());
    expect(sendResize).toHaveBeenCalledWith(80, 24);
  });

  it("syncs the size to the PTY once the connection opens", () => {
    render(<TerminalPanel voyageId="v1" />);
    // connection is "open" from mount → an initial resize is pushed.
    expect(sendResize).toHaveBeenCalledWith(80, 24);
  });

  it("disposes the terminal on unmount", () => {
    const { unmount } = render(<TerminalPanel voyageId="v1" />);
    unmount();
    expect(termInstance.dispose).toHaveBeenCalledTimes(1);
  });

  it("shows the connection status", () => {
    render(<TerminalPanel voyageId="v1" />);
    expect(screen.getByText(/terminal connected/i)).toBeInTheDocument();
  });
});
