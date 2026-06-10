// Ship's Log row model + pure merge/filter/search helpers.
//
// Contracts:
//  P3  dedupe by event_id (REST row carries details.event_id; live event's
//      event_id matches).
//  P13 sort by created_at (ms) with id tie-break; canonical for REST + WS rows.
//  P9  REST history reconciles with best-effort WS deltas — merge is idempotent.

import type { CrewActionRead, EventEnvelope } from "./types";

export type LogRow = {
  event_id: string;
  id: string;
  createdAt: number; // ms
  crewMember: string;
  actionType: string;
  summary: string;
  details: Record<string, unknown> | null;
  phaseNumber: number | null;
};

function phaseOf(details: Record<string, unknown> | null | undefined): number | null {
  const p = details?.phase_number;
  return typeof p === "number" ? p : null;
}

export function rowFromCrewAction(a: CrewActionRead): LogRow {
  const eventId =
    typeof a.details?.event_id === "string" ? (a.details.event_id as string) : a.id;
  return {
    event_id: eventId,
    id: a.id,
    createdAt: Date.parse(a.created_at),
    crewMember: a.crew_member,
    actionType: a.action_type,
    summary: a.summary,
    details: a.details,
    phaseNumber: phaseOf(a.details),
  };
}

export function rowFromEvent(e: EventEnvelope): LogRow | null {
  // Dial System failover isn't a crew_action_recorded, but users should see it
  // in the log — synthesize a row directly from the provider_switched event.
  if (e.type === "provider_switched") {
    const payload = e.payload as Record<string, unknown>;
    const provider =
      typeof payload.new_provider === "string" ? payload.new_provider : "another provider";
    const model = typeof payload.new_model === "string" ? payload.new_model : null;
    return {
      event_id: e.event_id,
      id: e.event_id,
      createdAt: e.ts,
      crewMember: e.source_role,
      actionType: "provider_switched",
      summary: model
        ? `Switched provider → ${provider}/${model}`
        : `Switched provider → ${provider}`,
      details: payload,
      phaseNumber: null,
    };
  }
  if (e.type !== "crew_action_recorded") return null;
  const p = e.payload as Record<string, unknown>;
  const details = (p.details as Record<string, unknown> | null) ?? null;
  return {
    event_id: (p.event_id as string) ?? e.event_id,
    id: (p.crew_action_id as string) ?? e.event_id,
    createdAt: typeof p.created_at === "string" ? Date.parse(p.created_at as string) : e.ts,
    crewMember: e.source_role,
    actionType: (p.action_type as string) ?? e.type,
    summary: (p.summary as string) ?? "",
    details,
    phaseNumber: phaseOf(details),
  };
}

// Merge durable REST rows with live WS rows, dedupe by event_id (REST wins),
// sort newest-first by (createdAt desc, id desc) (P13).
export function mergeLog(
  restRows: LogRow[],
  liveRows: LogRow[],
): LogRow[] {
  const byId = new Map<string, LogRow>();
  for (const r of liveRows) byId.set(r.event_id, r);
  for (const r of restRows) byId.set(r.event_id, r); // REST is canonical
  return Array.from(byId.values()).sort((a, b) =>
    a.createdAt !== b.createdAt
      ? b.createdAt - a.createdAt
      : a.id < b.id
        ? 1
        : a.id > b.id
          ? -1
          : 0,
  );
}

export type LogFilters = {
  crewRoles: string[]; // empty = all
  phase: number | null;
  failureOnly: boolean;
  search: string;
};

export const EMPTY_FILTERS: LogFilters = {
  crewRoles: [],
  phase: null,
  failureOnly: false,
  search: "",
};

function isFailure(row: LogRow): boolean {
  return /fail/i.test(row.actionType);
}

export function applyFilters(rows: LogRow[], f: LogFilters): LogRow[] {
  const q = f.search.trim().toLowerCase();
  return rows.filter((r) => {
    if (f.crewRoles.length && !f.crewRoles.includes(r.crewMember)) return false;
    if (f.phase !== null && r.phaseNumber !== f.phase) return false;
    if (f.failureOnly && !isFailure(r)) return false;
    if (q) {
      const haystack = `${r.summary} ${r.actionType} ${r.crewMember} ${
        r.phaseNumber ?? ""
      } ${JSON.stringify(r.details ?? {})}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }
    return true;
  });
}
