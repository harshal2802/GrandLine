"use client";

import { useCallback, useEffect, useRef } from "react";
import { Terminal } from "@xterm/xterm";
import { FitAddon } from "@xterm/addon-fit";
import "@xterm/xterm/css/xterm.css";
import { useCabinTerminal } from "@/hooks/useCabinTerminal";

// Phase B3 — the interactive terminal surface. Mounts an `xterm.js` Terminal and
// bridges it over a bidirectional WebSocket to a real PTY inside the user's gVisor
// Cabin. Keystrokes (xterm `onData`) flow out as `{"type":"input",...}`; PTY output
// (`{"type":"output",...}`) is written to the term. A FitAddon + ResizeObserver keep
// the PTY window sized to the container (`{"type":"resize",...}`). The shell runs
// INSIDE the isolated Cabin — this view never sees a secret, only the PTY byte stream.
interface TerminalPanelProps {
  voyageId: string | null;
}

export function TerminalPanel({ voyageId }: TerminalPanelProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const termRef = useRef<Terminal | null>(null);
  const fitRef = useRef<FitAddon | null>(null);

  const enabled = voyageId !== null;

  const writeOutput = useCallback((data: string) => {
    termRef.current?.write(data);
  }, []);

  const { connection, sendInput, sendResize } = useCabinTerminal({
    voyageId,
    enabled,
    onOutput: writeOutput,
  });

  // Keep the latest senders without re-mounting the term on each render.
  const sendInputRef = useRef(sendInput);
  const sendResizeRef = useRef(sendResize);
  useEffect(() => {
    sendInputRef.current = sendInput;
    sendResizeRef.current = sendResize;
  }, [sendInput, sendResize]);

  // Mount xterm once the container exists; tear it down cleanly on unmount.
  useEffect(() => {
    if (!enabled || !containerRef.current) return;

    const term = new Terminal({
      cursorBlink: true,
      fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
      fontSize: 13,
      theme: { background: "#0a1424" },
    });
    const fit = new FitAddon();
    term.loadAddon(fit);
    term.open(containerRef.current);
    try {
      fit.fit();
    } catch {
      /* container not measurable yet */
    }
    termRef.current = term;
    fitRef.current = fit;

    const dataSub = term.onData((data) => sendInputRef.current(data));

    // Forward terminal dimensions to the PTY whenever they change.
    const emitResize = () => sendResizeRef.current(term.cols, term.rows);
    const resizeSub = term.onResize(emitResize);

    const observer = new ResizeObserver(() => {
      try {
        fit.fit();
      } catch {
        /* ignore transient measurement errors */
      }
    });
    observer.observe(containerRef.current);

    // Initial sync once the WS opens (handled below via `connection`).
    return () => {
      observer.disconnect();
      dataSub.dispose();
      resizeSub.dispose();
      term.dispose();
      termRef.current = null;
      fitRef.current = null;
    };
  }, [enabled]);

  // On (re)connect, push the current size so the PTY matches the visible term.
  useEffect(() => {
    if (connection === "open" && termRef.current) {
      sendResizeRef.current(termRef.current.cols, termRef.current.rows);
    }
  }, [connection]);

  if (!voyageId) {
    return (
      <div className="rounded-lg border border-ocean-800 bg-ocean-900/40 p-6 text-sm text-ocean-300">
        Select a voyage to open a terminal in its Cabin.
      </div>
    );
  }

  return (
    <section className="space-y-2">
      <div className="flex items-center justify-between gap-2 text-xs text-ocean-400">
        <span className="inline-flex items-center gap-1.5">
          <span
            className={`h-2 w-2 rounded-full ${
              connection === "open" ? "bg-emerald-400" : "bg-ocean-600"
            }`}
          />
          Terminal {connection === "open" ? "connected" : connection}
        </span>
        <span className="text-ocean-500">Runs inside your isolated Cabin</span>
      </div>
      <div
        ref={containerRef}
        data-testid="terminal-surface"
        className="h-[60vh] w-full overflow-hidden rounded-lg border border-ocean-800 bg-ocean-950 p-2"
      />
    </section>
  );
}
