// Transport-agnostic live event hook (CONTRACTS P1/P2/P4/P10).
//
// WS first. Three handshake failures within 60s → sticky SSE fallback. Auth
// close (1008 or close within 5s of open) → refresh + reconnect. Terminal close
// (1000 + reason "voyage-terminal") → terminal-idle, no retry. Manual
// reconnect() always retries WS first.

"use client";

import { useCallback, useEffect, useRef } from "react";
import { WS_V1, API_V1 } from "@/lib/config";
import { readCookie } from "@/lib/auth/cookie";
import { normalizeFrame } from "@/lib/eventEnvelope";
import type { RawEventFrame, Transport } from "@/lib/types";
import { useAuthStore } from "@/stores/auth";
import { useVoyageStore } from "@/stores/voyage";

const HANDSHAKE_GRACE_MS = 5_000;
const FAIL_WINDOW_MS = 60_000;
const MAX_WS_FAILS = 3;
const QUIET_WINDOW_MS = 500; // first-connect replay→live (P2)
const RECONNECT_BACKOFF_MS = 1_000;

type StreamControls = { reconnect: () => void; disconnect: () => void };

function currentToken(): string | null {
  return useAuthStore.getState().accessToken ?? readCookie("access_token");
}

export function useVoyageStream(voyageId: string | null): StreamControls {
  const wsRef = useRef<WebSocket | null>(null);
  const sseRef = useRef<AbortController | null>(null);
  const quietTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const openedAt = useRef<number>(0);
  const failTimes = useRef<number[]>([]);
  const transport = useRef<Transport>("ws");
  const stoppedRef = useRef(false);

  const store = useVoyageStore;

  const clearTimers = useCallback(() => {
    if (quietTimer.current) clearTimeout(quietTimer.current);
    if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
    quietTimer.current = null;
    reconnectTimer.current = null;
  }, []);

  const teardown = useCallback(() => {
    clearTimers();
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.onopen = null;
      try {
        wsRef.current.close();
      } catch {
        /* noop */
      }
      wsRef.current = null;
    }
    if (sseRef.current) {
      sseRef.current.abort();
      sseRef.current = null;
    }
  }, [clearTimers]);

  const scheduleQuietMarkLive = useCallback(
    (id: string) => {
      if (quietTimer.current) clearTimeout(quietTimer.current);
      quietTimer.current = setTimeout(() => store.getState().markLive(id), QUIET_WINDOW_MS);
    },
    [store],
  );

  const handleEvent = useCallback(
    (id: string, frame: RawEventFrame) => {
      const env = normalizeFrame(frame, false); // store decides isReplay (P2)
      store.getState().ingest(id, env);
      scheduleQuietMarkLive(id);
    },
    [store, scheduleQuietMarkLive],
  );

  const connectSse = useCallback(
    (id: string) => {
      transport.current = "sse";
      store.getState().setTransport("sse");
      store.getState().setConnectionState("connecting");
      store.getState().beginConnection(id);

      const ctrl = new AbortController();
      sseRef.current = ctrl;
      const token = currentToken();

      fetch(`${API_V1}/voyages/${id}/stream`, {
        signal: ctrl.signal,
        headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        credentials: "include",
      })
        .then(async (res) => {
          if (!res.ok || !res.body) {
            store.getState().setConnectionState("closed");
            return;
          }
          store.getState().setConnectionState("open");
          const reader = res.body.getReader();
          const decoder = new TextDecoder();
          let buffer = "";
          for (;;) {
            const { done, value } = await reader.read();
            if (done) break;
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() ?? "";
            for (const line of lines) {
              const trimmed = line.startsWith("data:") ? line.slice(5).trim() : "";
              if (!trimmed) continue;
              try {
                const frame = JSON.parse(trimmed) as RawEventFrame;
                if (frame.type === "event") handleEvent(id, frame);
              } catch {
                /* ignore keep-alive / malformed lines */
              }
            }
          }
          store.getState().setConnectionState("closed");
        })
        .catch(() => {
          if (!ctrl.signal.aborted) store.getState().setConnectionState("closed");
        });
    },
    [store, handleEvent],
  );

  const connectWs = useCallback(
    (id: string) => {
      const token = currentToken();
      if (!token) {
        store.getState().setConnectionState("closed");
        return;
      }
      transport.current = "ws";
      store.getState().setTransport("ws");
      store.getState().setConnectionState("connecting");
      store.getState().beginConnection(id);

      const ws = new WebSocket(`${WS_V1}/voyages/${id}/events?token=${encodeURIComponent(token)}`);
      wsRef.current = ws;
      let opened = false;

      ws.onopen = () => {
        opened = true;
        openedAt.current = Date.now();
        store.getState().setConnectionState("open");
      };

      ws.onmessage = (ev) => {
        try {
          const frame = JSON.parse(ev.data as string) as RawEventFrame;
          if (frame.type === "event") handleEvent(id, frame);
        } catch {
          /* ignore */
        }
      };

      ws.onclose = (ev) => {
        wsRef.current = null;
        if (stoppedRef.current) return;

        // Terminal closure (P10) — stop, no retry.
        if (ev.code === 1000 && ev.reason === "voyage-terminal") {
          store.getState().setConnectionState("terminal-idle");
          return;
        }

        const quickClose = opened && Date.now() - openedAt.current < HANDSHAKE_GRACE_MS;
        const authClose = ev.code === 1008 || quickClose;

        // Auth close → refresh + reconnect with a fresh token (P4).
        if (authClose) {
          void useAuthStore
            .getState()
            .refresh()
            .then((ok) => {
              if (ok && !stoppedRef.current) connectWs(id);
              else store.getState().setConnectionState("closed");
            });
          return;
        }

        // Handshake failure (never opened) — count toward SSE fallback (P1).
        if (!opened) {
          const now = Date.now();
          failTimes.current = failTimes.current.filter((t) => now - t < FAIL_WINDOW_MS);
          failTimes.current.push(now);
          if (failTimes.current.length >= MAX_WS_FAILS) {
            connectSse(id); // sticky for the connection lifetime
            return;
          }
        }

        // Transient drop on a running voyage — reconnect with backoff (P1).
        store.getState().setConnectionState("reconnecting");
        reconnectTimer.current = setTimeout(() => {
          if (!stoppedRef.current) connectWs(id);
        }, RECONNECT_BACKOFF_MS);
      };

      ws.onerror = () => {
        // Surfaced via onclose; nothing to do here.
      };
    },
    [store, handleEvent, connectSse],
  );

  const start = useCallback(
    (id: string) => {
      stoppedRef.current = false;
      failTimes.current = [];
      teardown();
      connectWs(id); // always WS first
    },
    [teardown, connectWs],
  );

  const reconnect = useCallback(() => {
    if (!voyageId) return;
    // Manual reconnect on a terminal voyage no-ops (P10).
    const status = store.getState().buffers[voyageId]?.status;
    if (status && ["COMPLETED", "FAILED", "CANCELLED"].includes(status)) return;
    transport.current = "ws";
    start(voyageId);
  }, [voyageId, start, store]);

  const disconnect = useCallback(() => {
    stoppedRef.current = true;
    teardown();
    store.getState().setConnectionState("idle");
  }, [teardown, store]);

  useEffect(() => {
    if (!voyageId) return;
    start(voyageId);
    return () => {
      stoppedRef.current = true;
      teardown();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [voyageId]);

  return { reconnect, disconnect };
}
