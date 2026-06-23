"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DIAL_PROVIDERS,
  DIAL_ROLES,
  getDialConfig,
  getDialStatus,
  updateDialConfig,
  type DialProvider,
  type FallbackEntry,
  type ProviderWindowUsage,
  type RoleProviderConfig,
} from "@/lib/dial";
import {
  SEA_CHEST_KINDS,
  disconnectCredential,
  type CredentialStatus,
  type SeaChestKind,
} from "@/lib/seaChest";
import { useSeaChest } from "@/hooks/useSeaChest";
import { useClaudeLogin } from "@/hooks/useClaudeLogin";

// A fallback entry, always normalized to the object form for editing.
type FallbackObj = { provider: string; model?: string };

function normalizeEntry(entry: FallbackEntry): FallbackObj {
  if (typeof entry === "string") return { provider: entry };
  return entry.model ? { provider: entry.provider, model: entry.model } : { provider: entry.provider };
}

// Per-voyage Dial System panel: view/edit role→provider mapping (writes through
// PUT /dial-config, taking effect on the next LLM call), edit fallback chains, set a
// per-role claude_code max_turns (C1), watch per-provider rate-limit headroom (#54), and
// see/disconnect per-user Sea Chest credentials (C2). The connect flows are C0/A3.
export function DialPanel({ voyageId }: { voyageId: string }) {
  const queryClient = useQueryClient();

  const configQuery = useQuery({
    queryKey: ["dial-config", voyageId],
    queryFn: () => getDialConfig(voyageId),
    retry: false,
  });
  const statusQuery = useQuery({
    queryKey: ["dial-status", voyageId],
    queryFn: () => getDialStatus(voyageId),
    refetchInterval: 15000,
    retry: false,
  });

  const [draft, setDraft] = useState<Record<string, RoleProviderConfig>>({});
  const [fallbackDraft, setFallbackDraft] = useState<Record<string, FallbackObj[]>>({});
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (configQuery.data) {
      setDraft({ ...configQuery.data.role_mapping });
      const seeded: Record<string, FallbackObj[]> = {};
      for (const [role, entries] of Object.entries(configQuery.data.fallback_chain ?? {})) {
        seeded[role] = entries.map(normalizeEntry);
      }
      setFallbackDraft(seeded);
    }
  }, [configQuery.data]);

  const mutation = useMutation({
    mutationFn: (body: {
      role_mapping: Record<string, RoleProviderConfig>;
      fallback_chain: Record<string, FallbackEntry[]>;
    }) => updateDialConfig(voyageId, body),
    onSuccess: () => {
      setSaved(true);
      void queryClient.invalidateQueries({ queryKey: ["dial-config", voyageId] });
      setTimeout(() => setSaved(false), 2500);
    },
  });

  if (configQuery.isLoading) {
    return <p className="text-xs text-ocean-400">Loading dial config…</p>;
  }
  if (configQuery.isError || !configQuery.data) {
    return (
      <p className="text-xs text-ocean-400">
        No dial config for this voyage yet. It is created when the voyage is charted.
      </p>
    );
  }

  const config = configQuery.data;
  // Seed both drafts from the persisted config for the dirty check.
  const persistedFallback: Record<string, FallbackObj[]> = {};
  for (const [role, entries] of Object.entries(config.fallback_chain ?? {})) {
    persistedFallback[role] = entries.map(normalizeEntry);
  }
  const dirty =
    JSON.stringify(draft) !== JSON.stringify(config.role_mapping) ||
    JSON.stringify(fallbackDraft) !== JSON.stringify(persistedFallback);
  // PUT replaces role_mapping wholesale and the router rejects any role missing a
  // provider or model — block the save instead of bricking the voyage's routing. A
  // stray max_turns is ignored by this guard (only provider+model are required).
  const incomplete = Object.values(draft).some(
    (c) => !c.provider || !c.model.trim(),
  );
  const usageByProvider = new Map<string, ProviderWindowUsage>(
    (statusQuery.data?.providers ?? []).map((p) => [p.provider, p]),
  );

  const setRole = (role: string, patch: Partial<RoleProviderConfig>) => {
    setDraft((d) => {
      const base = d[role] ?? { provider: "anthropic", model: "" };
      const next: RoleProviderConfig = { ...base, ...patch };
      // Switching away from claude_code drops the claude-only knob.
      if (next.provider !== "claude_code") delete next.max_turns;
      return { ...d, [role]: next };
    });
  };

  const setMaxTurns = (role: string, raw: string) => {
    const n = Number.parseInt(raw, 10);
    if (raw === "" || Number.isNaN(n)) {
      setDraft((d) => {
        const base = d[role] ?? { provider: "anthropic", model: "" };
        const next = { ...base };
        delete next.max_turns;
        return { ...d, [role]: next };
      });
      return;
    }
    setRole(role, { max_turns: Math.min(10, Math.max(1, n)) });
  };

  const addFallback = (role: string) => {
    setFallbackDraft((f) => ({
      ...f,
      [role]: [...(f[role] ?? []), { provider: DIAL_PROVIDERS[0] }],
    }));
  };

  const removeFallback = (role: string, index: number) => {
    setFallbackDraft((f) => ({
      ...f,
      [role]: (f[role] ?? []).filter((_, i) => i !== index),
    }));
  };

  const setFallbackEntry = (role: string, index: number, patch: Partial<FallbackObj>) => {
    setFallbackDraft((f) => {
      const list = [...(f[role] ?? [])];
      const base = list[index] ?? { provider: DIAL_PROVIDERS[0] };
      const next: FallbackObj = { ...base, ...patch };
      if (next.model !== undefined && next.model.trim() === "") delete next.model;
      list[index] = next;
      return { ...f, [role]: list };
    });
  };

  const save = () => {
    // Normalize the fallback draft to wire entries, dropping empty roles' arrays only
    // if they were never seeded (preserve explicit [] so removals persist).
    const fallback_chain: Record<string, FallbackEntry[]> = {};
    for (const [role, list] of Object.entries(fallbackDraft)) {
      fallback_chain[role] = list.map((e) =>
        e.model ? { provider: e.provider, model: e.model } : { provider: e.provider },
      );
    }
    mutation.mutate({ role_mapping: draft, fallback_chain });
  };

  return (
    <div className="space-y-4">
      <section>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-ocean-400">
          Role → provider
        </h4>
        <div className="space-y-2">
          {DIAL_ROLES.map((role) => {
            const cfg = draft[role];
            const isClaudeCode = cfg?.provider === "claude_code";
            const fallbacks = fallbackDraft[role] ?? [];
            return (
              <div key={role} className="space-y-1.5 border-b border-ocean-800/60 pb-2 last:border-0">
                <div className="flex items-center gap-2">
                  <span className="w-20 shrink-0 text-xs capitalize text-ocean-300">{role}</span>
                  <select
                    value={cfg?.provider ?? ""}
                    onChange={(e) => setRole(role, { provider: e.target.value as DialProvider })}
                    className="w-28 shrink-0 rounded border border-ocean-700 bg-ocean-950 px-1.5 py-1 text-xs text-ocean-100 outline-none focus:border-ocean-400"
                  >
                    <option value="" disabled>
                      —
                    </option>
                    {DIAL_PROVIDERS.map((p) => (
                      <option key={p} value={p}>
                        {p}
                      </option>
                    ))}
                  </select>
                  <input
                    value={cfg?.model ?? ""}
                    onChange={(e) => setRole(role, { model: e.target.value })}
                    placeholder="model"
                    className="min-w-0 flex-1 rounded border border-ocean-700 bg-ocean-950 px-1.5 py-1 text-xs text-ocean-100 outline-none focus:border-ocean-400"
                  />
                  {isClaudeCode && (
                    <label className="flex shrink-0 items-center gap-1 text-[11px] text-ocean-400">
                      <span>max turns</span>
                      <input
                        type="number"
                        min={1}
                        max={10}
                        aria-label={`${role} max turns`}
                        value={cfg?.max_turns ?? ""}
                        onChange={(e) => setMaxTurns(role, e.target.value)}
                        placeholder="—"
                        className="w-12 rounded border border-ocean-700 bg-ocean-950 px-1.5 py-1 text-xs text-ocean-100 outline-none focus:border-ocean-400"
                      />
                    </label>
                  )}
                </div>
                <div className="flex flex-wrap items-center gap-1.5 pl-20">
                  <span className="text-[11px] uppercase tracking-wide text-ocean-500">fallback</span>
                  {fallbacks.length === 0 && (
                    <span className="text-[11px] text-ocean-600">none</span>
                  )}
                  {fallbacks.map((entry, i) => (
                    <span
                      key={i}
                      className="flex items-center gap-1 rounded border border-ocean-700 bg-ocean-900 px-1 py-0.5 text-[11px]"
                    >
                      <select
                        value={entry.provider}
                        aria-label={`${role} fallback ${i + 1} provider`}
                        onChange={(e) => setFallbackEntry(role, i, { provider: e.target.value })}
                        className="rounded bg-ocean-950 text-[11px] text-ocean-100 outline-none"
                      >
                        {DIAL_PROVIDERS.map((p) => (
                          <option key={p} value={p}>
                            {p}
                          </option>
                        ))}
                      </select>
                      <input
                        value={entry.model ?? ""}
                        aria-label={`${role} fallback ${i + 1} model`}
                        onChange={(e) => setFallbackEntry(role, i, { model: e.target.value })}
                        placeholder="model"
                        className="w-20 rounded bg-ocean-950 px-1 text-[11px] text-ocean-100 outline-none"
                      />
                      <button
                        type="button"
                        aria-label={`remove fallback ${i + 1} from ${role}`}
                        onClick={() => removeFallback(role, i)}
                        className="text-ocean-500 hover:text-rose-400"
                      >
                        ✕
                      </button>
                    </span>
                  ))}
                  <button
                    type="button"
                    aria-label={`add fallback to ${role}`}
                    onClick={() => addFallback(role)}
                    className="rounded border border-ocean-700 px-1.5 py-0.5 text-[11px] text-ocean-300 hover:border-ocean-400 hover:text-ocean-100"
                  >
                    + add
                  </button>
                </div>
              </div>
            );
          })}
        </div>
        <div className="mt-2 flex items-center gap-2">
          <button
            disabled={!dirty || incomplete || mutation.isPending}
            onClick={save}
            className="rounded bg-ocean-500 px-3 py-1 text-xs text-ocean-950 hover:bg-ocean-400 disabled:opacity-50"
          >
            {mutation.isPending ? "Saving…" : "Save config"}
          </button>
          {incomplete ? (
            <span className="text-xs text-rose-400">Every role needs a provider and model</span>
          ) : (
            dirty && <span className="text-xs text-amber-400">Unsaved changes</span>
          )}
          {saved && !dirty && <span className="text-xs text-emerald-400">Saved ✓</span>}
          {mutation.isError && (
            <span className="text-xs text-rose-400">
              {mutation.error instanceof Error ? mutation.error.message : "Save failed"}
            </span>
          )}
        </div>
        <p className="mt-1 text-[11px] text-ocean-500">
          Takes effect on the next LLM call. Fallbacks try in order after the primary.
        </p>
      </section>

      <SeaChestSection />

      <section>
        <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-ocean-400">
          Rate-limit headroom
          {statusQuery.data && (
            <span className="ml-1 normal-case text-ocean-500">
              · {statusQuery.data.window_seconds}s window
            </span>
          )}
        </h4>
        {statusQuery.isError ? (
          <p className="text-xs text-ocean-500">Usage unavailable.</p>
        ) : usageByProvider.size === 0 ? (
          <p className="text-xs text-ocean-500">No providers configured.</p>
        ) : (
          <div className="space-y-2">
            {Array.from(usageByProvider.values()).map((u) => (
              <ProviderUsage key={u.provider} usage={u} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

// Sea Chest connection status (Phase 0a, surfaced in C2). Shows whether the user has
// connected each credential kind and lets them disconnect. The `claude_code` Connect is
// now REAL (Phase C0): it runs the device-login inside the user's Cabin, shows the
// verification URL/code, and polls until connected. GitHub OAuth (A3 UI) stays a disabled
// "coming soon" affordance. The API NEVER returns a secret/token.
function SeaChestSection() {
  const queryClient = useQueryClient();
  const query = useSeaChest();

  const disconnect = useMutation({
    mutationFn: (kind: SeaChestKind) => disconnectCredential(kind),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["sea-chest"] });
    },
  });

  const byKind = new Map<string, CredentialStatus>(
    (query.data ?? []).map((c) => [c.kind, c]),
  );

  return (
    <section>
      <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-ocean-400">
        Sea Chest · connections
      </h4>
      {query.isLoading ? (
        <p className="text-xs text-ocean-500">Loading connections…</p>
      ) : query.isError ? (
        <p className="text-xs text-ocean-500">Connection status unavailable.</p>
      ) : (
        <div className="space-y-2">
          {SEA_CHEST_KINDS.map((kind) => (
            <CredentialStatusRow
              key={kind}
              kind={kind}
              status={byKind.get(kind) ?? null}
              onDisconnect={() => disconnect.mutate(kind)}
              disconnecting={disconnect.isPending && disconnect.variables === kind}
            />
          ))}
          {disconnect.isError && (
            <p className="text-xs text-rose-400">
              {disconnect.error instanceof Error
                ? disconnect.error.message
                : "Disconnect failed"}
            </p>
          )}
        </div>
      )}
    </section>
  );
}

interface CredentialStatusRowProps {
  kind: SeaChestKind;
  status: CredentialStatus | null;
  onDisconnect: () => void;
  disconnecting: boolean;
}

const KIND_LABELS: Record<SeaChestKind, string> = {
  claude_code: "Claude Code",
  github: "GitHub",
};

function CredentialStatusRow({
  kind,
  status,
  onDisconnect,
  disconnecting,
}: CredentialStatusRowProps) {
  const connected = status?.connected ?? false;
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="w-24 shrink-0 text-ocean-300">{KIND_LABELS[kind]}</span>
      {connected ? (
        <>
          <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-300">
            Connected
          </span>
          {status?.label && <span className="text-ocean-400">{status.label}</span>}
          <button
            type="button"
            onClick={onDisconnect}
            disabled={disconnecting}
            className="ml-auto rounded border border-ocean-700 px-2 py-0.5 text-ocean-300 hover:border-rose-400 hover:text-rose-300 disabled:opacity-50"
          >
            {disconnecting ? "Disconnecting…" : "Disconnect"}
          </button>
        </>
      ) : kind === "claude_code" ? (
        <ClaudeConnect />
      ) : (
        <>
          <span className="rounded bg-ocean-800 px-1.5 py-0.5 text-ocean-400">
            Not connected
          </span>
          <span className="ml-auto flex items-center gap-1">
            <button
              type="button"
              disabled
              className="cursor-not-allowed rounded border border-ocean-800 px-2 py-0.5 text-ocean-600"
            >
              Connect
            </button>
            <span className="text-[11px] text-ocean-600">coming soon</span>
          </span>
        </>
      )}
    </div>
  );
}

// The REAL Claude Code connect flow (Phase C0): Connect → start the device-login in the
// Cabin → show the verification URL/code → poll until connected (then ["sea-chest"] is
// invalidated by the hook, flipping the row to Connected). No token ever reaches the UI.
function ClaudeConnect() {
  const { phase, start, error, begin, reset } = useClaudeLogin();

  if (phase === "idle" || phase === "error") {
    return (
      <>
        <span className="rounded bg-ocean-800 px-1.5 py-0.5 text-ocean-400">Not connected</span>
        <span className="ml-auto flex items-center gap-1">
          {phase === "error" && (
            <span className="text-[11px] text-rose-400">{error ?? "Login failed"}</span>
          )}
          <button
            type="button"
            onClick={begin}
            className="rounded border border-ocean-700 px-2 py-0.5 text-ocean-200 hover:border-ocean-400 hover:text-ocean-100"
          >
            {phase === "error" ? "Retry" : "Connect"}
          </button>
        </span>
      </>
    );
  }

  if (phase === "starting") {
    return (
      <>
        <span className="rounded bg-ocean-800 px-1.5 py-0.5 text-ocean-400">Not connected</span>
        <span className="ml-auto text-[11px] text-ocean-400">Starting login…</span>
      </>
    );
  }

  if (phase === "connected") {
    return (
      <>
        <span className="rounded bg-emerald-500/15 px-1.5 py-0.5 text-emerald-300">Connected</span>
        <span className="ml-auto text-[11px] text-emerald-300">Done ✓</span>
      </>
    );
  }

  // phase === "awaiting": show the verification URL/code and a Cancel.
  return (
    <span className="ml-auto flex flex-col items-end gap-0.5 text-[11px]">
      <span className="text-ocean-300">Open to approve:</span>
      {start && (
        <a
          href={start.verification_uri}
          target="_blank"
          rel="noreferrer"
          className="text-sky-300 underline hover:text-sky-200"
        >
          {start.verification_uri}
        </a>
      )}
      {start?.user_code && (
        <span className="text-ocean-200">
          code: <span className="font-mono">{start.user_code}</span>
        </span>
      )}
      <span className="flex items-center gap-1 text-ocean-500">
        <span>Waiting for approval…</span>
        <button
          type="button"
          onClick={reset}
          className="rounded border border-ocean-700 px-1.5 py-0.5 text-ocean-300 hover:border-rose-400 hover:text-rose-300"
        >
          Cancel
        </button>
      </span>
    </span>
  );
}

function ProviderUsage({ usage }: { usage: ProviderWindowUsage }) {
  const usedRequests = usage.max_requests - (usage.remaining_requests ?? usage.max_requests);
  const pct = usage.max_requests > 0 ? Math.round((usedRequests / usage.max_requests) * 100) : 0;
  return (
    <div>
      <div className="mb-0.5 flex items-center justify-between text-xs">
        <span className="text-ocean-200">{usage.provider}</span>
        {usage.is_limited ? (
          <span className="text-rose-400">rate limited</span>
        ) : (
          <span className="text-ocean-400">
            {usage.remaining_requests ?? "?"} req · {usage.remaining_tokens ?? "?"} tok left
          </span>
        )}
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-ocean-800">
        <div
          className={`h-full rounded-full ${usage.is_limited ? "bg-rose-500" : "bg-emerald-400"}`}
          style={{ width: `${Math.min(100, pct)}%` }}
        />
      </div>
    </div>
  );
}
