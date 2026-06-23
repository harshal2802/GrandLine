// Live preview log streaming (Phase B1) over the SSE endpoint
// GET /voyages/{id}/preview/logs/stream. The backend polls PreviewService.logs and
// emits only NEW lines as `data: <line>\n\n` frames.
//
// EventSource can't set an Authorization header, so — like useVoyageStream's SSE
// fallback — we read the stream via fetch + a ReadableStream reader with the bearer
// token from the auth store. Lines accumulate into a capped buffer; `follow` controls
// whether the consumer should auto-scroll. The fetch is aborted on unmount / when the
// stream is disabled, so no reader leaks.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { API_V1 } from "@/lib/config";
import { readCookie } from "@/lib/auth/cookie";
import { useAuthStore } from "@/stores/auth";

const MAX_LINES = 5_000; // ring buffer — drop oldest beyond this.

export type PreviewLogConnection = "idle" | "connecting" | "open" | "closed";

export interface UsePreviewLogs {
  lines: string[];
  connection: PreviewLogConnection;
  follow: boolean;
  setFollow: (follow: boolean) => void;
  clear: () => void;
}

function currentToken(): string | null {
  return useAuthStore.getState().accessToken ?? readCookie("access_token");
}

export function usePreviewLogs(
  voyageId: string | null,
  enabled: boolean,
): UsePreviewLogs {
  const [lines, setLines] = useState<string[]>([]);
  const [connection, setConnection] = useState<PreviewLogConnection>("idle");
  const [follow, setFollow] = useState(true);
  const abortRef = useRef<AbortController | null>(null);

  const clear = useCallback(() => setLines([]), []);

  const append = useCallback((incoming: string[]) => {
    if (incoming.length === 0) return;
    setLines((prev) => {
      const next = prev.concat(incoming);
      return next.length > MAX_LINES ? next.slice(next.length - MAX_LINES) : next;
    });
  }, []);

  useEffect(() => {
    if (!voyageId || !enabled) {
      setConnection("idle");
      return;
    }

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setConnection("connecting");
    const token = currentToken();

    fetch(`${API_V1}/voyages/${voyageId}/preview/logs/stream`, {
      signal: ctrl.signal,
      headers: token ? { Authorization: `Bearer ${token}` } : undefined,
      credentials: "include",
    })
      .then(async (res) => {
        if (!res.ok || !res.body) {
          setConnection("closed");
          return;
        }
        setConnection("open");
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const frames = buffer.split("\n");
          buffer = frames.pop() ?? "";
          const batch: string[] = [];
          for (const frame of frames) {
            if (frame.startsWith("data:")) batch.push(frame.slice(5).replace(/^ /, ""));
          }
          append(batch);
        }
        setConnection("closed");
      })
      .catch(() => {
        if (!ctrl.signal.aborted) setConnection("closed");
      });

    return () => {
      ctrl.abort();
      abortRef.current = null;
    };
  }, [voyageId, enabled, append]);

  return { lines, connection, follow, setFollow, clear };
}
