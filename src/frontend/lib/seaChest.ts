// Sea Chest API client + types (mirrors app/schemas/sea_chest.py CredentialStatus —
// Phase 0a). The deck reads per-user credential CONNECTION STATUS and can disconnect
// a credential. The API NEVER returns a secret or ciphertext; only non-secret metadata
// (kind, connected, label hint, timestamps). The connect flows themselves — device-code
// `claude login` (C0) and GitHub OAuth (A3) — are later phases.

import { apiFetch } from "@/lib/api";

export const SEA_CHEST_KINDS = ["claude_code", "github"] as const;
export type SeaChestKind = (typeof SEA_CHEST_KINDS)[number];

// Secret-free status, exactly as the backend returns it. There is NO secret field.
export type CredentialStatus = {
  kind: SeaChestKind;
  connected: boolean;
  label: string | null;
  created_at: string;
  last_used_at: string | null;
};

export function getSeaChest() {
  return apiFetch<CredentialStatus[]>(`/sea-chest`);
}

export function disconnectCredential(kind: SeaChestKind) {
  return apiFetch<void>(`/sea-chest/${kind}`, { method: "DELETE" });
}
