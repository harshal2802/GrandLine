import type { VoyageStatus } from "@/lib/types";

// Color-independent status indicator (PLAN P7 a11y): each status pairs a glyph
// with a label so it reads without relying on color alone.
const META: Record<VoyageStatus, { glyph: string; cls: string }> = {
  CHARTED: { glyph: "○", cls: "text-ocean-400" },
  PLANNING: { glyph: "◔", cls: "text-sky-300" },
  PDD: { glyph: "◑", cls: "text-sky-300" },
  TDD: { glyph: "◑", cls: "text-indigo-300" },
  BUILDING: { glyph: "◕", cls: "text-amber-300" },
  REVIEWING: { glyph: "◕", cls: "text-violet-300" },
  DEPLOYING: { glyph: "◕", cls: "text-cyan-300" },
  COMPLETED: { glyph: "●", cls: "text-emerald-400" },
  FAILED: { glyph: "✕", cls: "text-rose-400" },
  PAUSED: { glyph: "❚❚", cls: "text-amber-400" },
  CANCELLED: { glyph: "⊘", cls: "text-ocean-500" },
};

export function StatusBadge({ status }: { status: VoyageStatus }) {
  const meta = META[status] ?? META.CHARTED;
  return (
    <span className={`inline-flex items-center gap-1 text-xs font-medium ${meta.cls}`}>
      <span aria-hidden>{meta.glyph}</span>
      {status}
    </span>
  );
}
