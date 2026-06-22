// Dial System API client + types (mirrors app/schemas/dial_config.py and
// app/schemas/dial_system.py). The deck reads/writes a voyage's role→provider
// mapping and reads per-provider rate-limit headroom.

import { apiFetch } from "@/lib/api";
import type { CrewRole } from "@/lib/types";

export const DIAL_PROVIDERS = [
  "anthropic",
  "openai",
  "ollama",
  "claude_code",
] as const;
export type DialProvider = (typeof DIAL_PROVIDERS)[number];

export const DIAL_ROLES: readonly CrewRole[] = [
  "captain",
  "navigator",
  "doctor",
  "shipwright",
  "helmsman",
];

export type RoleProviderConfig = {
  provider: string;
  model: string;
  // C1: a per-role behavioral knob for the `claude_code` provider, carried inside
  // the role's `role_mapping` entry (role_mapping is JSONB; the backend resolver
  // tolerates the extra key). Bounded 1–10; absent for non-claude_code roles.
  max_turns?: number;
};
export type FallbackEntry = string | { provider: string; model?: string };

export type DialConfig = {
  id: string;
  voyage_id: string;
  role_mapping: Record<string, RoleProviderConfig>;
  fallback_chain: Record<string, FallbackEntry[]> | null;
  created_at: string;
  updated_at: string;
};

export type DialConfigUpdate = {
  role_mapping?: Record<string, RoleProviderConfig>;
  fallback_chain?: Record<string, FallbackEntry[]> | null;
};

export type ProviderWindowUsage = {
  provider: string;
  is_limited: boolean;
  remaining_requests: number | null;
  remaining_tokens: number | null;
  max_requests: number;
  max_tokens: number;
};

export type DialStatus = {
  voyage_id: string;
  window_seconds: number;
  providers: ProviderWindowUsage[];
};

export function getDialConfig(voyageId: string) {
  return apiFetch<DialConfig>(`/voyages/${voyageId}/dial-config`);
}

export function updateDialConfig(voyageId: string, body: DialConfigUpdate) {
  return apiFetch<DialConfig>(`/voyages/${voyageId}/dial-config`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export function getDialStatus(voyageId: string) {
  return apiFetch<DialStatus>(`/voyages/${voyageId}/dial-status`);
}

// Render a fallback entry compactly (provider or provider/model).
export function fallbackLabel(entry: FallbackEntry): string {
  if (typeof entry === "string") return entry;
  return entry.model ? `${entry.provider}/${entry.model}` : entry.provider;
}
