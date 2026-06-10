"use client";

import { useEffect, useRef, useState } from "react";
import { useActiveVoyageEvents } from "@/hooks/useActiveVoyageEvents";
import { useVoyageStore } from "@/stores/voyage";
import { useFocusStore } from "@/stores/focus";
import { CREW_ROLES, type CrewRole, type EventEnvelope } from "@/lib/types";
import { EmptyState } from "./EmptyState";

type Node = { role: CrewRole; label: string; glyph: string; x: number; y: number };

// Hand-positioned crew along the voyage flow (PLAN Phase 3).
const NODES: Node[] = [
  { role: "captain", label: "Captain", glyph: "🧭", x: 90, y: 90 },
  { role: "navigator", label: "Navigator", glyph: "🗺️", x: 270, y: 60 },
  { role: "doctor", label: "Doctor", glyph: "🩺", x: 450, y: 110 },
  { role: "shipwright", label: "Shipwright", glyph: "🔨", x: 630, y: 60 },
  { role: "helmsman", label: "Helmsman", glyph: "⚙️", x: 810, y: 100 },
];

const EDGES: [CrewRole, CrewRole][] = [
  ["captain", "navigator"],
  ["navigator", "doctor"],
  ["doctor", "shipwright"],
  ["shipwright", "helmsman"],
];

const ACTIVITY_LABEL: Record<string, string> = {
  voyage_plan_created: "Charting the course…",
  poneglyph_drafted: "Drafting Poneglyphs…",
  health_check_written: "Writing health checks…",
  phase_build_started: "Building…",
  code_generated: "Generating code…",
  tests_passed: "Tests green ✓",
  phase_build_failed: "Build failed ✕",
  validation_passed: "Validation passed ✓",
  validation_failed: "Validation failed ✕",
  deployment_started: "Deploying…",
  deployment_completed: "Deployed ✓",
  deployment_failed: "Deploy failed ✕",
  pipeline_stage_entered: "Entering stage…",
  provider_switched: "Switched provider ⚡",
};

function nodeOf(role: CrewRole): Node | undefined {
  return NODES.find((n) => n.role === role);
}

export function CrewMap() {
  const events = useActiveVoyageEvents();
  const activeId = useVoyageStore((s) => s.activeVoyageId);
  const setHoveredCrew = useFocusStore((s) => s.setHoveredCrew);
  const hoveredCrew = useFocusStore((s) => s.hoveredCrew);

  const [flashRole, setFlashRole] = useState<CrewRole | null>(null);
  const [activeRole, setActiveRole] = useState<CrewRole | null>(null);
  const [label, setLabel] = useState<{ role: CrewRole; text: string } | null>(null);
  const seenCount = useRef(0);
  const labelTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const flashTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // React to newly-arrived LIVE events only (P2: replays don't animate).
  useEffect(() => {
    if (events.length <= seenCount.current) {
      seenCount.current = events.length;
      return;
    }
    const fresh = events.slice(seenCount.current);
    seenCount.current = events.length;
    const liveLast = [...fresh].reverse().find((e) => !e.isReplay);
    if (!liveLast) return;

    setActiveRole(liveLast.source_role);
    setFlashRole(liveLast.source_role);
    setLabel({ role: liveLast.source_role, text: ACTIVITY_LABEL[liveLast.type] ?? liveLast.type });

    if (flashTimer.current) clearTimeout(flashTimer.current);
    flashTimer.current = setTimeout(() => setFlashRole(null), 600);
    if (labelTimer.current) clearTimeout(labelTimer.current);
    labelTimer.current = setTimeout(() => setLabel(null), 2000);
  }, [events]);

  // Reset transient state on voyage switch.
  useEffect(() => {
    seenCount.current = 0;
    setActiveRole(null);
    setFlashRole(null);
    setLabel(null);
  }, [activeId]);

  // Rolling 60s recent-event counters (live events only, P2).
  const now = Date.now();
  const counts: Record<string, number> = {};
  for (const e of events) {
    if (e.isReplay) continue;
    if (now - e.ts > 60_000) continue;
    counts[e.source_role] = (counts[e.source_role] ?? 0) + 1;
  }

  if (!activeId) {
    return <EmptyState title="Select a voyage" hint="Pick a voyage to watch the crew at work." icon="🗺️" />;
  }

  return (
    <div className="h-full">
      <svg viewBox="0 0 900 200" className="h-auto w-full" role="img" aria-label="Crew map showing agent activity">
        {/* Edges */}
        {EDGES.map(([from, to]) => {
          const a = nodeOf(from)!;
          const b = nodeOf(to)!;
          const flashing = flashRole === to;
          return (
            <line
              key={`${from}-${to}`}
              x1={a.x}
              y1={a.y}
              x2={b.x}
              y2={b.y}
              stroke={flashing ? "#34d399" : "#1e3a4f"}
              strokeWidth={flashing ? 3 : 1.5}
              className="transition-all duration-300"
              aria-hidden
            />
          );
        })}

        {/* Nodes */}
        {NODES.map((n) => {
          const isActive = activeRole === n.role;
          const isHovered = hoveredCrew === n.role;
          const recent = counts[n.role] ?? 0;
          return (
            <g
              key={n.role}
              onMouseEnter={() => setHoveredCrew(n.role)}
              onMouseLeave={() => setHoveredCrew(null)}
              className="cursor-pointer"
              tabIndex={0}
              aria-label={`${n.label}${isActive ? " (active)" : ""}, ${recent} recent events`}
            >
              <circle
                cx={n.x}
                cy={n.y}
                r={26}
                fill={isActive ? "#0e7490" : "#0c4a6e"}
                stroke={isHovered ? "#7dd3fc" : isActive ? "#34d399" : "#155e75"}
                strokeWidth={isHovered || isActive ? 3 : 1.5}
                className={isActive ? "animate-pulse" : ""}
              />
              <text x={n.x} y={n.y + 6} textAnchor="middle" fontSize="20" aria-hidden>
                {n.glyph}
              </text>
              <text x={n.x} y={n.y + 44} textAnchor="middle" fontSize="11" fill="#7dd3fc">
                {n.label}
              </text>
              {recent > 0 && (
                <>
                  <circle cx={n.x + 22} cy={n.y - 20} r={9} fill="#f59e0b" aria-hidden />
                  <text x={n.x + 22} y={n.y - 16} textAnchor="middle" fontSize="10" fill="#1c1917" aria-hidden>
                    {recent}
                  </text>
                </>
              )}
              {label?.role === n.role && (
                <text x={n.x} y={n.y - 36} textAnchor="middle" fontSize="11" fill="#fbbf24">
                  {label.text}
                </text>
              )}
            </g>
          );
        })}
      </svg>

      <CrewLegend counts={counts} events={events} />
    </div>
  );
}

function CrewLegend({ counts, events }: { counts: Record<string, number>; events: EventEnvelope[] }) {
  return (
    <div className="mt-6 flex flex-wrap gap-3 text-xs text-ocean-400">
      {CREW_ROLES.map((r) => (
        <span key={r} className="rounded bg-ocean-900/60 px-2 py-1">
          {r}: <span className="text-ocean-200">{counts[r] ?? 0}</span> recent
        </span>
      ))}
      <span className="rounded bg-ocean-900/60 px-2 py-1">
        total events: <span className="text-ocean-200">{events.length}</span>
      </span>
    </div>
  );
}
