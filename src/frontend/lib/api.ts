// REST fetch wrapper (CONTRACTS P4). Injects the bearer token from the auth
// store *at call time*; on 401 it refreshes once and retries; if the refresh
// fails it clears the store and redirects to /login?redirect=<current path>.

import { API_V1 } from "@/lib/config";
import { useAuthStore } from "@/stores/auth";

export class ApiError extends Error {
  status: number;
  code?: string;
  constructor(status: number, message: string, code?: string) {
    super(message);
    this.status = status;
    this.code = code;
  }
}

function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const here = window.location.pathname + window.location.search;
  window.location.href = `/login?redirect=${encodeURIComponent(here)}`;
}

function withAuth(init: RequestInit): RequestInit {
  const token = useAuthStore.getState().accessToken;
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return { ...init, headers, credentials: "include" };
}

export async function apiFetch<T = unknown>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const url = path.startsWith("http") ? path : `${API_V1}${path}`;

  let res = await fetch(url, withAuth(init));

  if (res.status === 401) {
    const refreshed = await useAuthStore.getState().refresh();
    if (!refreshed) {
      redirectToLogin();
      throw new ApiError(401, "session expired");
    }
    res = await fetch(url, withAuth(init));
    if (res.status === 401) {
      redirectToLogin();
      throw new ApiError(401, "session expired");
    }
  }

  if (!res.ok) {
    const body = await res.json().catch(() => null);
    const err = body?.detail?.error;
    throw new ApiError(
      res.status,
      err?.message ?? `request failed (${res.status})`,
      err?.code,
    );
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}
