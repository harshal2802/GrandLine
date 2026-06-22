// Shared domain types for the Observation Deck. Mirrors the backend schemas
// (app/schemas/observation_deck.py, app/den_den_mushi/events.py).

export type CrewRole =
  | "captain"
  | "navigator"
  | "doctor"
  | "shipwright"
  | "helmsman";

export type VoyageStatus =
  | "CHARTED"
  | "PLANNING"
  | "PDD"
  | "TDD"
  | "BUILDING"
  | "REVIEWING"
  | "DEPLOYING"
  | "COMPLETED"
  | "FAILED"
  | "PAUSED"
  | "CANCELLED";

// Deployment tiers (mirrors app/schemas/deployment.py DeploymentTier).
export type DeployTier = "preview" | "staging" | "production";

export const DEPLOY_TIERS: readonly DeployTier[] = ["preview", "staging", "production"];

export const TERMINAL_STATUSES: ReadonlySet<VoyageStatus> = new Set<VoyageStatus>([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
]);

export function isTerminal(status: VoyageStatus | undefined): boolean {
  return status !== undefined && TERMINAL_STATUSES.has(status);
}

// Canonical normalized event (CONTRACTS P3). `event_id` is the only dedupe key;
// display sort is (ts asc, msg_id asc).
export type EventEnvelope = {
  event_id: string;
  msg_id: string;
  ts: number; // ms since epoch, from backend `timestamp`
  source_role: CrewRole;
  type: string; // backend event_type
  payload: Record<string, unknown>;
  isReplay: boolean; // P2 — snapshotted at receipt
};

// Raw WS frame as sent by the backend forwarder.
export type RawEventFrame = {
  type: "event";
  payload: {
    msg_id: string;
    event: {
      event_id: string;
      event_type: string;
      voyage_id: string;
      timestamp: string;
      source_role: CrewRole;
      payload: Record<string, unknown>;
    };
  };
};

export type VoyageListItem = {
  id: string;
  title: string;
  description: string | null;
  status: VoyageStatus;
  target_repo: string | null;
  phase_status: Record<string, string>;
  created_at: string;
  updated_at: string;
};

export type CrewActionRead = {
  id: string;
  voyage_id: string;
  crew_member: string;
  action_type: string;
  summary: string;
  details: Record<string, unknown> | null;
  created_at: string;
};

// A single file the Shipwright produced for a phase (mirrors
// app/schemas/build_artifact.py BuildArtifactRead). snake_case as the API returns it.
// Powers the Changes view — the always-available, no-git code browser (Phase A1).
export type BuildArtifact = {
  id: string;
  voyage_id: string;
  shipwright_run_id: string;
  phase_number: number;
  file_path: string;
  content: string;
  language: string;
  created_by: string;
  created_at: string;
};

// Real git diffs (Phase A2) — mirrors the backend schemas in
// app/schemas/git.py (GitChangedFile / GitDiff / GitFileContent). snake_case as
// the API returns it. Surfaced in the Changes view's Diff mode; falls back to
// the A1 artifacts view when a voyage didn't use git.
export type GitChangedFile = {
  path: string;
  status: string; // A / M / D / R… from `git diff --name-status`
};

export type GitDiff = {
  base: string;
  head: string;
  path: string | null;
  unified: string;
};

export type GitFileContent = {
  ref: string;
  path: string;
  content: string;
};

export type Paginated<T> = {
  items: T[];
  nextCursor: string | null;
};

export type AuthUser = {
  id: string;
  email: string;
  username: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
};

export type TokenPair = {
  access_token: string;
  refresh_token: string;
  token_type: string;
};

export type Transport = "ws" | "sse";

export type ConnectionState =
  | "idle"
  | "connecting"
  | "open"
  | "reconnecting"
  | "terminal-idle"
  | "closed";

export const CREW_ROLES: CrewRole[] = [
  "captain",
  "navigator",
  "doctor",
  "shipwright",
  "helmsman",
];
