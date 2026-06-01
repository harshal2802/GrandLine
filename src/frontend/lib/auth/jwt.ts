// Client-side JWT decode for pre-emptive refresh (CONTRACTS P4). No signature
// verification — the server still validates. We only read `exp` to schedule a
// refresh before the 30-minute access token expires.

export type JwtClaims = {
  sub?: string;
  exp?: number; // seconds since epoch
  type?: string;
  [k: string]: unknown;
};

function base64UrlDecode(segment: string): string {
  const padded = segment.replace(/-/g, "+").replace(/_/g, "/");
  const pad = padded.length % 4 === 0 ? "" : "=".repeat(4 - (padded.length % 4));
  const b64 = padded + pad;
  if (typeof atob === "function") {
    return atob(b64);
  }
  // Node fallback (tests).
  return Buffer.from(b64, "base64").toString("binary");
}

export function decodeJwt(token: string): JwtClaims | null {
  const parts = token.split(".");
  if (parts.length !== 3) return null;
  try {
    return JSON.parse(base64UrlDecode(parts[1])) as JwtClaims;
  } catch {
    return null;
  }
}

// Milliseconds until the token expires. Returns 0 if already expired or no exp.
export function expiresInMs(token: string, now: number = Date.now()): number {
  const claims = decodeJwt(token);
  if (!claims?.exp) return 0;
  return Math.max(0, claims.exp * 1000 - now);
}
