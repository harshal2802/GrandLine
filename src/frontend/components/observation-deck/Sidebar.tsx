"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { useVoyages } from "@/hooks/useVoyages";
import { StatusBadge } from "./StatusBadge";

export function Sidebar() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const active = params.get("voyage");

  const { data, isLoading, error, fetchNextPage, hasNextPage } = useVoyages({
    queryKey: "sidebar",
    limit: 50,
  });

  const voyages = data?.pages.flatMap((p) => p.items) ?? [];

  const select = (id: string) => {
    const next = new URLSearchParams(params.toString());
    next.set("voyage", id);
    router.push(`${pathname}?${next.toString()}`);
  };

  return (
    <aside className="flex w-64 shrink-0 flex-col border-r border-ocean-800 bg-ocean-900/60">
      <div className="border-b border-ocean-800 px-4 py-3">
        <h2 className="text-sm font-semibold uppercase tracking-wider text-ocean-400">
          Voyages
        </h2>
      </div>
      <nav className="flex-1 overflow-y-auto p-2" aria-label="Voyages">
        {isLoading && <p className="px-2 py-3 text-sm text-ocean-500">Loading…</p>}
        {error && (
          <p className="px-2 py-3 text-sm text-rose-400">Failed to load voyages</p>
        )}
        {!isLoading && voyages.length === 0 && (
          <p className="px-2 py-3 text-sm text-ocean-500">No voyages yet.</p>
        )}
        <ul className="space-y-1">
          {voyages.map((v) => (
            <li key={v.id}>
              <button
                onClick={() => select(v.id)}
                aria-current={active === v.id ? "true" : undefined}
                className={`flex w-full flex-col gap-1 rounded-md px-3 py-2 text-left transition-colors ${
                  active === v.id
                    ? "bg-ocean-700/60 text-ocean-50"
                    : "text-ocean-300 hover:bg-ocean-800/60"
                }`}
              >
                <span className="truncate text-sm font-medium">{v.title}</span>
                <StatusBadge status={v.status} />
              </button>
            </li>
          ))}
        </ul>
        {hasNextPage && (
          <button
            onClick={() => fetchNextPage()}
            className="mt-2 w-full rounded-md border border-ocean-700 px-3 py-1.5 text-xs text-ocean-300 hover:bg-ocean-800"
          >
            Show more voyages
          </button>
        )}
      </nav>
    </aside>
  );
}
