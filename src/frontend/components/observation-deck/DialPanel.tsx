"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  DIAL_PROVIDERS,
  DIAL_ROLES,
  fallbackLabel,
  getDialConfig,
  getDialStatus,
  updateDialConfig,
  type DialProvider,
  type ProviderWindowUsage,
  type RoleProviderConfig,
} from "@/lib/dial";

// Per-voyage Dial System panel: view/edit role→provider mapping (writes through
// PUT /dial-config, taking effect on the next LLM call), see fallback chains,
// and watch per-provider rate-limit headroom (#54).
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
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (configQuery.data) setDraft({ ...configQuery.data.role_mapping });
  }, [configQuery.data]);

  const mutation = useMutation({
    mutationFn: (mapping: Record<string, RoleProviderConfig>) =>
      updateDialConfig(voyageId, { role_mapping: mapping }),
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
  const dirty = JSON.stringify(draft) !== JSON.stringify(config.role_mapping);
  // PUT replaces role_mapping wholesale and the router rejects any role missing
  // a provider or model — block the save instead of bricking the voyage's routing.
  const incomplete = Object.values(draft).some(
    (c) => !c.provider || !c.model.trim(),
  );
  const usageByProvider = new Map<string, ProviderWindowUsage>(
    (statusQuery.data?.providers ?? []).map((p) => [p.provider, p]),
  );

  const setRole = (role: string, patch: Partial<RoleProviderConfig>) => {
    setDraft((d) => {
      const base = d[role] ?? { provider: "anthropic", model: "" };
      return { ...d, [role]: { ...base, ...patch } };
    });
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
            return (
              <div key={role} className="flex items-center gap-2">
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
              </div>
            );
          })}
        </div>
        <div className="mt-2 flex items-center gap-2">
          <button
            disabled={!dirty || incomplete || mutation.isPending}
            onClick={() => mutation.mutate(draft)}
            className="rounded bg-ocean-500 px-3 py-1 text-xs text-ocean-950 hover:bg-ocean-400 disabled:opacity-50"
          >
            {mutation.isPending ? "Saving…" : "Save mapping"}
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
        <p className="mt-1 text-[11px] text-ocean-500">Takes effect on the next LLM call.</p>
      </section>

      {config.fallback_chain && Object.keys(config.fallback_chain).length > 0 && (
        <section>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-ocean-400">
            Fallback chains
          </h4>
          <div className="space-y-1 text-xs">
            {Object.entries(config.fallback_chain).map(([role, entries]) => (
              <div key={role} className="flex items-baseline gap-2">
                <span className="w-20 shrink-0 capitalize text-ocean-300">{role}</span>
                <span className="text-ocean-200">
                  {entries.map(fallbackLabel).join(" → ") || "—"}
                </span>
              </div>
            ))}
          </div>
        </section>
      )}

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
