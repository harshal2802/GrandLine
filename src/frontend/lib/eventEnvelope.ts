// Normalize a raw backend WS/SSE event into the canonical EventEnvelope
// (CONTRACTS P3). The same function serves both transports so a frame parses
// identically regardless of where it came from (P1).

import type { EventEnvelope, RawEventFrame } from "./types";

type RawEvent = RawEventFrame["payload"]["event"];

export function normalizeEvent(
  msgId: string,
  event: RawEvent,
  isReplay: boolean,
): EventEnvelope {
  return {
    event_id: event.event_id,
    msg_id: msgId,
    ts: Date.parse(event.timestamp),
    source_role: event.source_role,
    type: event.event_type,
    payload: event.payload ?? {},
    isReplay,
  };
}

export function normalizeFrame(
  frame: RawEventFrame,
  isReplay: boolean,
): EventEnvelope {
  return normalizeEvent(frame.payload.msg_id, frame.payload.event, isReplay);
}

// Canonical display ordering (P3): timestamp asc, msg_id asc as tie-break.
export function compareEnvelopes(a: EventEnvelope, b: EventEnvelope): number {
  if (a.ts !== b.ts) return a.ts - b.ts;
  return a.msg_id < b.msg_id ? -1 : a.msg_id > b.msg_id ? 1 : 0;
}
