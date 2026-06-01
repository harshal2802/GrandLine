// Runtime configuration for the Observation Deck client.
//
// Base URLs are read from NEXT_PUBLIC_* env vars so the same build can target
// local dev (:8000) or a same-origin prod proxy. Defaults match `make api-dev`.

export const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

// WS base derives from the API base unless explicitly overridden. http→ws,
// https→wss.
export const WS_BASE_URL =
  process.env.NEXT_PUBLIC_WS_BASE_URL ??
  API_BASE_URL.replace(/^http(s?):\/\//, (_m, s) => `ws${s}://`);

export const API_V1 = `${API_BASE_URL}/api/v1`;
export const WS_V1 = `${WS_BASE_URL}/api/v1`;
