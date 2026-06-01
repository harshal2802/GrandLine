// Typed, schema-versioned localStorage wrapper. Every stored object carries a
// `__version` field; a version mismatch falls back to the default so a schema
// change never throws on stale data (PLAN cross-cutting: state persistence).

const PREFIX = "observation_deck";

type Versioned<T> = T & { __version: number };

export function readPref<T>(key: string, version: number, fallback: T): T {
  if (typeof localStorage === "undefined") return fallback;
  try {
    const raw = localStorage.getItem(`${PREFIX}.${key}`);
    if (!raw) return fallback;
    const parsed = JSON.parse(raw) as Versioned<T>;
    if (parsed.__version !== version) return fallback;
    const { __version, ...rest } = parsed;
    void __version;
    return rest as T;
  } catch {
    return fallback;
  }
}

export function writePref<T>(key: string, version: number, value: T): void {
  if (typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(
      `${PREFIX}.${key}`,
      JSON.stringify({ ...value, __version: version }),
    );
  } catch {
    // Quota / private mode — preferences are best-effort.
  }
}

// Poll interval options for Ship's Log reconciliation (P9).
export const POLL_INTERVAL_OPTIONS = [0, 30_000, 60_000, 120_000] as const;
export type PollInterval = (typeof POLL_INTERVAL_OPTIONS)[number];
