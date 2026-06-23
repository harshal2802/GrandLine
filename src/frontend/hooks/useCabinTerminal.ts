// Interactive Cabin terminal WS lifecycle (Phase B3).
//
// Opens a bidirectional WebSocket to `/voyages/{id}/terminal` authenticated via the
// `grandline-bearer` subprotocol (the token never rides the URL, mirroring
// useVoyageStream). Inbound `{"type":"output","data"}` frames are handed to `onOutput`;
// the caller pushes user keystrokes via `sendInput` and window changes via `sendResize`.
// The socket is torn down cleanly on unmount or when `voyageId`/`enabled` change.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { WS_V1 } from "@/lib/config";
import { readCookie } from "@/lib/auth/cookie";
import { useAuthStore } from "@/stores/auth";

export type TerminalConnection = "idle" | "connecting" | "open" | "closed";

interface UseCabinTerminalOptions {
  voyageId: string | null;
  enabled: boolean;
  onOutput: (data: string) => void;
}

interface CabinTerminalControls {
  connection: TerminalConnection;
  sendInput: (data: string) => void;
  sendResize: (cols: number, rows: number) => void;
}

function currentToken(): string | null {
  return useAuthStore.getState().accessToken ?? readCookie("access_token");
}

export function useCabinTerminal({
  voyageId,
  enabled,
  onOutput,
}: UseCabinTerminalOptions): CabinTerminalControls {
  const wsRef = useRef<WebSocket | null>(null);
  const [connection, setConnection] = useState<TerminalConnection>("idle");

  // Keep the latest onOutput without re-opening the socket when it changes.
  const onOutputRef = useRef(onOutput);
  useEffect(() => {
    onOutputRef.current = onOutput;
  }, [onOutput]);

  const send = useCallback((frame: Record<string, unknown>) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify(frame));
    }
  }, []);

  const sendInput = useCallback(
    (data: string) => send({ type: "input", data }),
    [send],
  );

  const sendResize = useCallback(
    (cols: number, rows: number) => send({ type: "resize", cols, rows }),
    [send],
  );

  useEffect(() => {
    if (!voyageId || !enabled) {
      setConnection("idle");
      return;
    }
    const token = currentToken();
    if (!token) {
      setConnection("closed");
      return;
    }

    setConnection("connecting");
    // Token rides in the subprotocol list, never the URL (proxy logs / history).
    const ws = new WebSocket(`${WS_V1}/voyages/${voyageId}/terminal`, [
      "grandline-bearer",
      token,
    ]);
    wsRef.current = ws;

    ws.onopen = () => setConnection("open");

    ws.onmessage = (ev) => {
      try {
        const frame = JSON.parse(ev.data as string) as {
          type?: string;
          data?: string;
        };
        if (frame.type === "output" && typeof frame.data === "string") {
          onOutputRef.current(frame.data);
        }
      } catch {
        /* ignore malformed frames */
      }
    };

    ws.onclose = () => {
      if (wsRef.current === ws) wsRef.current = null;
      setConnection("closed");
    };

    ws.onerror = () => {
      /* surfaced via onclose */
    };

    return () => {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onclose = null;
      ws.onerror = null;
      try {
        ws.close();
      } catch {
        /* noop */
      }
      if (wsRef.current === ws) wsRef.current = null;
    };
  }, [voyageId, enabled]);

  return { connection, sendInput, sendResize };
}
