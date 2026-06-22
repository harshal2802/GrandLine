"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useUiStore } from "@/stores/ui";
import { usePlaybackStore } from "@/stores/playback";
import { shouldIgnoreShortcut } from "@/lib/shortcuts";

type Command = { id: string; label: string; run: () => void };

export function CommandPalette() {
  const router = useRouter();
  const params = useSearchParams();
  const open = useUiStore((s) => s.paletteOpen);
  const setPalette = useUiStore((s) => s.setPalette);
  const togglePalette = useUiStore((s) => s.togglePalette);
  const toggleFocusMode = useUiStore((s) => s.toggleFocusMode);
  const toggleHelp = useUiStore((s) => s.toggleHelp);
  const toggleFleet = useUiStore((s) => s.toggleFleet);
  const setFleet = useUiStore((s) => s.setFleet);
  const returnToLive = usePlaybackStore((s) => s.returnToLive);

  const [query, setQuery] = useState("");
  const inputRef = useRef<HTMLInputElement>(null);
  const chord = useRef<string | null>(null);

  const qs = params.get("voyage") ? `?voyage=${params.get("voyage")}` : "";
  const go = (path: string) => router.push(`${path}${qs}`);

  const commands: Command[] = [
    { id: "sea-chart", label: "Go to Sea Chart", run: () => go("/app/sea-chart") },
    { id: "crew-map", label: "Go to Crew Map", run: () => go("/app/crew-map") },
    { id: "ships-log", label: "Go to Ship's Log", run: () => go("/app/ships-log") },
    { id: "fleet", label: "Open Fleet Switcher", run: toggleFleet },
    { id: "live", label: "Return to live", run: returnToLive },
    { id: "focus", label: "Toggle focus mode", run: toggleFocusMode },
    { id: "help", label: "Keyboard shortcuts", run: toggleHelp },
  ];

  // Global key handling: Cmd/Ctrl-K palette, chords, single keys (P14 guard).
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if (shouldIgnoreShortcut(e, document.activeElement)) return;

      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        togglePalette();
        return;
      }
      if (e.key === "Escape") {
        setPalette(false);
        useUiStore.setState({ helpOpen: false, fleetOpen: false });
        chord.current = null;
        return;
      }
      if (open) return; // palette handles its own typing

      // Chord: `g` then s/c/l/f.
      if (chord.current === "g") {
        chord.current = null;
        if (e.key === "s") return go("/app/sea-chart");
        if (e.key === "c") return go("/app/crew-map");
        if (e.key === "l") return go("/app/ships-log");
        if (e.key === "f") return setFleet(true); // g f → Fleet Switcher
        return;
      }
      if (e.key === "g") {
        chord.current = "g";
        setTimeout(() => (chord.current = null), 800);
        return;
      }
      if (e.key === "f") return toggleFocusMode();
      if (e.key === "?") return toggleHelp();
      if (e.key === "/") {
        const search = document.querySelector<HTMLInputElement>('input[type="search"]');
        if (search) {
          e.preventDefault();
          search.focus();
        }
      }
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, qs]);

  useEffect(() => {
    if (open) {
      setQuery("");
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  if (!open) return null;

  const filtered = commands.filter((c) =>
    c.label.toLowerCase().includes(query.toLowerCase()),
  );

  return (
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-32" role="dialog" aria-label="Command palette">
      <div className="absolute inset-0 bg-black/50" onClick={() => setPalette(false)} aria-hidden />
      <div className="relative w-full max-w-md overflow-hidden rounded-xl border border-ocean-700 bg-ocean-900 shadow-2xl">
        <input
          ref={inputRef}
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Type a command…"
          className="w-full border-b border-ocean-800 bg-ocean-950 px-4 py-3 text-ocean-100 outline-none"
        />
        <ul className="max-h-72 overflow-auto py-1">
          {filtered.map((c) => (
            <li key={c.id}>
              <button
                onClick={() => {
                  c.run();
                  setPalette(false);
                }}
                className="w-full px-4 py-2 text-left text-sm text-ocean-200 hover:bg-ocean-800"
              >
                {c.label}
              </button>
            </li>
          ))}
          {filtered.length === 0 && (
            <li className="px-4 py-2 text-sm text-ocean-500">No commands</li>
          )}
        </ul>
      </div>
    </div>
  );
}
