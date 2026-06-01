// Voyage event store (Zustand) — the transport-agnostic heart of the deck.
//
// Contracts:
//  P2  replay vs live: per-voyage liveEpoch + replayMode; isReplay snapshotted
//      at ingest. Reconnect uses a msg_id cutover; first-ever connect uses a
//      quiet-window markLive() driven by the stream hook.
//  P3  canonical identity: dedupe by event_id (Map); display order (ts, msg_id).
//  P10 terminal closure: terminal status → connectionState "terminal-idle".
//  P12 buffer eviction: 5000-event ring buffer per voyage; events kept only for
//      active + 2 most recent voyages; global 15k cap drops oldest in LRU voyage.

import { create } from "zustand";
import type {
  ConnectionState,
  EventEnvelope,
  Transport,
  VoyageStatus,
} from "@/lib/types";
import { isTerminal } from "@/lib/types";

const RING_BUFFER = 5000;
const GLOBAL_CAP = 15_000;
const LRU_KEEP = 3; // active + 2 most recent

export type VoyageBuffer = {
  events: Map<string, EventEnvelope>; // dedupe by event_id (P3)
  order: string[]; // event_ids oldest→newest, for ring eviction
  maxKnownMsgId: string;
  cutoverMsgId: string; // maxKnownMsgId snapshot at connection start
  liveEpoch: number;
  replayMode: boolean;
  status?: VoyageStatus;
  lastEventTs: number | null;
};

type VoyageStoreState = {
  activeVoyageId: string | null;
  connectionState: ConnectionState;
  transport: Transport;
  buffers: Record<string, VoyageBuffer>;
  visitedOrder: string[]; // LRU, most-recent first

  selectVoyage: (id: string | null) => void;
  beginConnection: (voyageId: string) => void;
  ingest: (voyageId: string, raw: EventEnvelope) => void;
  markLive: (voyageId: string) => void;
  setConnectionState: (state: ConnectionState) => void;
  setTransport: (t: Transport) => void;
  setStatus: (voyageId: string, status: VoyageStatus) => void;
  getEvents: (voyageId: string) => EventEnvelope[];
  reset: () => void;
};

function emptyBuffer(): VoyageBuffer {
  return {
    events: new Map(),
    order: [],
    maxKnownMsgId: "",
    cutoverMsgId: "",
    liveEpoch: 0,
    replayMode: false,
    status: undefined,
    lastEventTs: null,
  };
}

function totalEvents(buffers: Record<string, VoyageBuffer>): number {
  let n = 0;
  for (const b of Object.values(buffers)) n += b.events.size;
  return n;
}

export const useVoyageStore = create<VoyageStoreState>((set, get) => ({
  activeVoyageId: null,
  connectionState: "idle",
  transport: "ws",
  buffers: {},
  visitedOrder: [],

  selectVoyage: (id) => {
    set((state) => {
      if (id === null) return { activeVoyageId: null };

      const buffers = { ...state.buffers };
      if (!buffers[id]) buffers[id] = emptyBuffer();

      // LRU: active + 2 most recent keep their events; others are cleared but
      // keep their status snapshot for sidebar rendering (P12).
      const visitedOrder = [
        id,
        ...state.visitedOrder.filter((v) => v !== id),
      ];
      const keep = new Set(visitedOrder.slice(0, LRU_KEEP));
      for (const [vid, buf] of Object.entries(buffers)) {
        if (!keep.has(vid) && buf.events.size > 0) {
          buffers[vid] = {
            ...buf,
            events: new Map(),
            order: [],
            lastEventTs: null,
          };
        }
      }

      return { activeVoyageId: id, buffers, visitedOrder };
    });
  },

  beginConnection: (voyageId) => {
    set((state) => {
      const buffers = { ...state.buffers };
      const prev = buffers[voyageId] ?? emptyBuffer();
      buffers[voyageId] = {
        ...prev,
        liveEpoch: prev.liveEpoch + 1,
        replayMode: true,
        cutoverMsgId: prev.maxKnownMsgId, // "" on first-ever connect
      };
      return { buffers };
    });
  },

  ingest: (voyageId, raw) => {
    set((state) => {
      const buffers = { ...state.buffers };
      const buf = { ...(buffers[voyageId] ?? emptyBuffer()) };
      buf.events = new Map(buf.events);
      buf.order = [...buf.order];

      // Determine isReplay (P2). During replayMode, a reconnect flips to live
      // on the first event with msg_id beyond the pre-connection cutover.
      // First-ever connect (cutoverMsgId === "") relies on markLive().
      let isReplay = buf.replayMode;
      if (buf.replayMode && buf.cutoverMsgId !== "" && raw.msg_id > buf.cutoverMsgId) {
        buf.replayMode = false;
        isReplay = false;
      }

      if (raw.msg_id > buf.maxKnownMsgId) buf.maxKnownMsgId = raw.msg_id;

      const env: EventEnvelope = { ...raw, isReplay };

      // Dedupe by event_id — keep first occurrence (P3).
      if (!buf.events.has(env.event_id)) {
        buf.events.set(env.event_id, env);
        buf.order.push(env.event_id);
        // Per-voyage ring buffer.
        while (buf.order.length > RING_BUFFER) {
          const evicted = buf.order.shift()!;
          buf.events.delete(evicted);
        }
        buf.lastEventTs = Math.max(buf.lastEventTs ?? 0, env.ts);
      }

      buffers[voyageId] = buf;

      // Global cap — drop oldest from the LRU voyage (P12).
      if (totalEvents(buffers) > GLOBAL_CAP) {
        const lru = [...state.visitedOrder].reverse();
        for (const vid of lru) {
          const b = buffers[vid];
          if (b && b.order.length > 0) {
            const nb = { ...b, events: new Map(b.events), order: [...b.order] };
            const evicted = nb.order.shift()!;
            nb.events.delete(evicted);
            buffers[vid] = nb;
            break;
          }
        }
      }

      return { buffers };
    });
  },

  markLive: (voyageId) => {
    set((state) => {
      const buf = state.buffers[voyageId];
      if (!buf || !buf.replayMode) return {};
      return {
        buffers: { ...state.buffers, [voyageId]: { ...buf, replayMode: false } },
      };
    });
  },

  setConnectionState: (connectionState) => set({ connectionState }),
  setTransport: (transport) => set({ transport }),

  setStatus: (voyageId, status) => {
    set((state) => {
      const buffers = { ...state.buffers };
      const buf = buffers[voyageId] ?? emptyBuffer();
      buffers[voyageId] = { ...buf, status };
      // Terminal status → terminal-idle, but only for the active voyage's live
      // connection (P10). A background voyage going terminal doesn't change the
      // chip for the one we're watching.
      const patch: Partial<VoyageStoreState> = { buffers };
      if (voyageId === state.activeVoyageId && isTerminal(status)) {
        patch.connectionState = "terminal-idle";
      }
      return patch;
    });
  },

  getEvents: (voyageId) => {
    const buf = get().buffers[voyageId];
    if (!buf) return [];
    return Array.from(buf.events.values()).sort((a, b) =>
      a.ts !== b.ts ? a.ts - b.ts : a.msg_id < b.msg_id ? -1 : a.msg_id > b.msg_id ? 1 : 0,
    );
  },

  reset: () =>
    set({
      activeVoyageId: null,
      connectionState: "idle",
      transport: "ws",
      buffers: {},
      visitedOrder: [],
    }),
}));
