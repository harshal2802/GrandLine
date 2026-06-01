"use client";

import Link from "next/link";
import { usePathname, useSearchParams } from "next/navigation";
import { useEffect } from "react";
import { useVoyageStream } from "@/hooks/useVoyageStream";
import { useVoyageStatus } from "@/hooks/useVoyageStatus";
import { useVoyageStore } from "@/stores/voyage";
import { usePlaybackStore } from "@/stores/playback";
import { useUiStore } from "@/stores/ui";
import { Sidebar } from "./Sidebar";
import { ConnectionState } from "./ConnectionState";
import { PlaybackControls } from "./PlaybackControls";
import { DetailsDrawer } from "./DetailsDrawer";
import { CommandPalette } from "./CommandPalette";
import { HelpDialog } from "./HelpDialog";
import { InterventionControls } from "./InterventionControls";

const TABS = [
  { href: "/app/sea-chart", label: "Sea Chart" },
  { href: "/app/crew-map", label: "Crew Map" },
  { href: "/app/ships-log", label: "Ship's Log" },
];

export function DeckShell({ children }: { children: React.ReactNode }) {
  const params = useSearchParams();
  const pathname = usePathname();
  const voyageId = params.get("voyage");

  // Drive the store's active voyage from the URL (Decision 6). On voyage switch
  // discard playback state and return to live (resolved open question).
  useEffect(() => {
    useVoyageStore.getState().selectVoyage(voyageId);
    usePlaybackStore.getState().resetForVoyage();
    usePlaybackStore.getState().closeDrawer();
  }, [voyageId]);

  useVoyageStatus(voyageId);
  const { reconnect } = useVoyageStream(voyageId);
  const focusMode = useUiStore((s) => s.focusMode);

  return (
    <div className="flex h-screen flex-col bg-ocean-950 text-ocean-100">
      <header className="flex items-center justify-between border-b border-ocean-800 bg-ocean-900 px-6 py-3">
        <div className="flex items-center gap-6">
          <span className="text-lg font-semibold text-ocean-100">
            ⚓ Observation Deck
          </span>
          <nav className="flex gap-1" aria-label="Deck views">
            {TABS.map((t) => {
              const activeTab = pathname.startsWith(t.href);
              const qs = voyageId ? `?voyage=${voyageId}` : "";
              return (
                <Link
                  key={t.href}
                  href={`${t.href}${qs}`}
                  aria-current={activeTab ? "page" : undefined}
                  className={`rounded-md px-3 py-1.5 text-sm transition-colors ${
                    activeTab
                      ? "bg-ocean-700 text-ocean-50"
                      : "text-ocean-300 hover:bg-ocean-800"
                  }`}
                >
                  {t.label}
                </Link>
              );
            })}
          </nav>
        </div>
        <div className="flex items-center gap-4">
          {voyageId && <InterventionControls voyageId={voyageId} />}
          <ConnectionState onReconnect={reconnect} />
        </div>
      </header>
      <div className="flex flex-1 overflow-hidden">
        {!focusMode && <Sidebar />}
        <main className="flex-1 overflow-auto p-6">{children}</main>
      </div>
      {voyageId && <PlaybackControls />}
      <DetailsDrawer />
      <CommandPalette />
      <HelpDialog />
    </div>
  );
}
