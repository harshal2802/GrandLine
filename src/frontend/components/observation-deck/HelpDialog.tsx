"use client";

import { useUiStore } from "@/stores/ui";

const SHORTCUTS: { keys: string; desc: string }[] = [
  { keys: "⌘/Ctrl K", desc: "Open command palette" },
  { keys: "g s", desc: "Go to Sea Chart" },
  { keys: "g c", desc: "Go to Crew Map" },
  { keys: "g l", desc: "Go to Ship's Log" },
  { keys: "/", desc: "Focus search" },
  { keys: "f", desc: "Toggle focus mode" },
  { keys: "?", desc: "Show this help" },
  { keys: "Esc", desc: "Close overlays" },
];

export function HelpDialog() {
  const open = useUiStore((s) => s.helpOpen);
  const toggle = useUiStore((s) => s.toggleHelp);
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center" role="dialog" aria-label="Keyboard shortcuts">
      <div className="absolute inset-0 bg-black/50" onClick={toggle} aria-hidden />
      <div className="relative w-full max-w-sm rounded-xl border border-ocean-700 bg-ocean-900 p-5 shadow-2xl">
        <h3 className="mb-3 text-sm font-semibold text-ocean-100">Keyboard shortcuts</h3>
        <ul className="space-y-1.5 text-sm">
          {SHORTCUTS.map((s) => (
            <li key={s.keys} className="flex items-center justify-between">
              <span className="text-ocean-300">{s.desc}</span>
              <kbd className="rounded bg-ocean-800 px-2 py-0.5 text-xs text-ocean-200">{s.keys}</kbd>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
