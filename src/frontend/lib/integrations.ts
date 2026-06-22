// Per-user integrations API client — Claude Code device-login in the Cabin (Phase C0).
// Mirrors app/schemas/integrations.py (ClaudeLoginStart / ClaudeLoginStatus). The
// user runs the Claude login inside their Cabin, approves at the verification URL, and
// the backend vaults the captured CLAUDE_CODE_OAUTH_TOKEN in the Sea Chest. The API
// NEVER returns the token: start carries the URL + an opaque login_id; poll carries a
// status + a non-secret label only.

import { apiFetch } from "@/lib/api";

// The login handshake to SHOW the user + poll with. No token field — there isn't one.
export type ClaudeLoginStart = {
  verification_uri: string;
  user_code: string | null;
  login_id: string;
};

// The outcome of a poll — NEVER carries the OAuth token.
export type ClaudeLoginStatus = {
  status: "pending" | "connected" | "error";
  label: string | null;
  error: string | null;
};

export function startClaudeLogin() {
  return apiFetch<ClaudeLoginStart>(`/integrations/claude/login/start`, {
    method: "POST",
  });
}

export function pollClaudeLogin(loginId: string) {
  return apiFetch<ClaudeLoginStatus>(`/integrations/claude/login/poll`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ login_id: loginId }),
  });
}
