// Auth store (Zustand). Holds the token pair + user, drives login/logout/
// refresh, and schedules a pre-emptive refresh ~60s before the access token's
// `exp` (CONTRACTS P4). Token is read from here at REST/WS call time.

import { create } from "zustand";
import { API_V1 } from "@/lib/config";
import { expiresInMs } from "@/lib/auth/jwt";
import type { AuthUser, TokenPair } from "@/lib/types";

// Fire the refresh this far before expiry (P4: "exp < 60s away").
const PREEMPT_MS = 60_000;

type AuthState = {
  accessToken: string | null;
  refreshToken: string | null;
  user: AuthUser | null;
  refreshTimer: ReturnType<typeof setTimeout> | null;

  setTokens: (pair: TokenPair) => void;
  setUser: (user: AuthUser | null) => void;
  fetchMe: () => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  register: (
    email: string,
    username: string,
    password: string,
  ) => Promise<void>;
  refresh: () => Promise<boolean>;
  logout: () => void;
  scheduleRefresh: () => void;
};

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${API_V1}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include", // let the backend set the access_token cookie
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.json().catch(() => null);
    throw new Error(
      detail?.detail?.error?.message ?? `request failed (${res.status})`,
    );
  }
  return (await res.json()) as T;
}

export const useAuthStore = create<AuthState>((set, get) => ({
  accessToken: null,
  refreshToken: null,
  user: null,
  refreshTimer: null,

  setTokens: (pair) => {
    set({ accessToken: pair.access_token, refreshToken: pair.refresh_token });
    get().scheduleRefresh();
  },

  setUser: (user) => set({ user }),

  fetchMe: async () => {
    const token = get().accessToken;
    if (!token) return;
    try {
      const res = await fetch(`${API_V1}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        credentials: "include",
      });
      if (res.ok) {
        set({ user: (await res.json()) as AuthUser });
      }
    } catch {
      // best-effort; the deck still works without the profile
    }
  },

  login: async (email, password) => {
    const pair = await postJson<TokenPair>("/auth/login", { email, password });
    get().setTokens(pair);
    await get().fetchMe();
  },

  register: async (email, username, password) => {
    const pair = await postJson<TokenPair>("/auth/register", {
      email,
      username,
      password,
    });
    get().setTokens(pair);
    await get().fetchMe();
  },

  refresh: async () => {
    const token = get().refreshToken;
    if (!token) return false;
    try {
      const pair = await postJson<TokenPair>("/auth/refresh", {
        refresh_token: token,
      });
      get().setTokens(pair);
      return true;
    } catch {
      get().logout();
      return false;
    }
  },

  logout: () => {
    const timer = get().refreshTimer;
    if (timer) clearTimeout(timer);
    set({
      accessToken: null,
      refreshToken: null,
      user: null,
      refreshTimer: null,
    });
  },

  scheduleRefresh: () => {
    const prev = get().refreshTimer;
    if (prev) clearTimeout(prev);
    const token = get().accessToken;
    if (!token) {
      set({ refreshTimer: null });
      return;
    }
    const lead = Math.max(0, expiresInMs(token) - PREEMPT_MS);
    const timer = setTimeout(() => {
      void get().refresh();
    }, lead);
    if (typeof timer === "object" && "unref" in timer) {
      (timer as { unref: () => void }).unref();
    }
    set({ refreshTimer: timer });
  },
}));
