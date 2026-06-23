// Claude Code device-login hook (Phase C0). Drives the connect flow from the DialPanel:
// start() runs `claude` login inside the user's Cabin and returns the verification URL +
// an opaque login_id; the user opens the URL out-of-band; the hook then polls until the
// backend reports `connected` (the captured CLAUDE_CODE_OAUTH_TOKEN is vaulted in the Sea
// Chest), at which point ["sea-chest"] is invalidated so the C2 status flips to Connected.
// The token NEVER reaches the browser — only the URL + a status.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  pollClaudeLogin,
  startClaudeLogin,
  type ClaudeLoginStart,
} from "@/lib/integrations";

export type ClaudeLoginPhase = "idle" | "starting" | "awaiting" | "connected" | "error";

export interface UseClaudeLogin {
  phase: ClaudeLoginPhase;
  start: ClaudeLoginStart | null;
  error: string | null;
  begin: () => void;
  reset: () => void;
}

const POLL_INTERVAL_MS = 2500;

export function useClaudeLogin(): UseClaudeLogin {
  const queryClient = useQueryClient();
  const [phase, setPhase] = useState<ClaudeLoginPhase>("idle");
  const [start, setStart] = useState<ClaudeLoginStart | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Track mount + the active login so a late poll never updates an unmounted/reset flow.
  const activeLoginId = useRef<string | null>(null);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const reset = useCallback(() => {
    activeLoginId.current = null;
    setPhase("idle");
    setStart(null);
    setError(null);
  }, []);

  const begin = useCallback(() => {
    setError(null);
    setStart(null);
    setPhase("starting");
    void (async () => {
      try {
        const started = await startClaudeLogin();
        if (!mounted.current) return;
        activeLoginId.current = started.login_id;
        setStart(started);
        setPhase("awaiting");
      } catch (e) {
        if (!mounted.current) return;
        activeLoginId.current = null;
        setError(e instanceof Error ? e.message : "Could not start Claude login");
        setPhase("error");
      }
    })();
  }, []);

  // Poll while awaiting approval.
  useEffect(() => {
    if (phase !== "awaiting") return;
    const loginId = activeLoginId.current;
    if (!loginId) return;

    let cancelled = false;
    const tick = async () => {
      try {
        const status = await pollClaudeLogin(loginId);
        if (cancelled || !mounted.current || activeLoginId.current !== loginId) return;
        if (status.status === "connected") {
          setPhase("connected");
          void queryClient.invalidateQueries({ queryKey: ["sea-chest"] });
        } else if (status.status === "error") {
          setError(status.error ?? "Claude login failed");
          setPhase("error");
        }
        // "pending" => keep polling on the interval.
      } catch (e) {
        if (cancelled || !mounted.current || activeLoginId.current !== loginId) return;
        setError(e instanceof Error ? e.message : "Polling failed");
        setPhase("error");
      }
    };

    const id = setInterval(tick, POLL_INTERVAL_MS);
    // Kick an immediate poll so a fast approval connects without waiting a full tick.
    void tick();
    return () => {
      cancelled = true;
      clearInterval(id);
    };
  }, [phase, queryClient]);

  return { phase, start, error, begin, reset };
}
