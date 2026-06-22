"use client";

import { useMemo, useState } from "react";
import { Highlight, themes } from "prism-react-renderer";
import { useBuildArtifacts } from "@/hooks/useBuildArtifacts";
import type { BuildArtifact } from "@/lib/types";

interface ChangesPanelProps {
  voyageId: string | null;
}

// Phase A1 — the "Changes" view. Lists every file the crew built (BuildArtifact
// {file_path, content, language, phase_number}, already stored + served),
// grouped by phase, with the selected file's content syntax-highlighted. This is
// the always-available, no-git code browser; real git diffs (A2) and per-user
// GitHub (A3) come later.
export function ChangesPanel({ voyageId }: ChangesPanelProps) {
  const query = useBuildArtifacts(voyageId);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const artifacts = useMemo(() => query.data ?? [], [query.data]);

  // Group by phase, ascending phase then file_path — stable for the list.
  const phases = useMemo(() => groupByPhase(artifacts), [artifacts]);

  const selected =
    artifacts.find((a) => a.id === selectedId) ?? artifacts[0] ?? null;

  if (query.isLoading) {
    return <p className="text-xs text-ocean-400">Charting the changes…</p>;
  }
  if (query.isError) {
    return (
      <p className="text-xs text-rose-400">
        Couldn&apos;t reach the changes — the build artifacts didn&apos;t load.
      </p>
    );
  }
  if (artifacts.length === 0) {
    return (
      <p className="text-xs text-ocean-400">
        No changes yet — the crew hasn&apos;t built any files.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <nav aria-label="Changed files" className="space-y-3">
        {phases.map(({ phase, files }) => (
          <div key={phase}>
            <p className="mb-1 text-[11px] font-medium uppercase tracking-wide text-ocean-400">
              Phase {phase}
            </p>
            <ul className="space-y-0.5">
              {files.map((a) => {
                const isActive = selected?.id === a.id;
                return (
                  <li key={a.id}>
                    <button
                      onClick={() => setSelectedId(a.id)}
                      aria-current={isActive ? "true" : undefined}
                      className={`w-full truncate rounded px-2 py-1 text-left text-xs ${
                        isActive
                          ? "bg-ocean-700 text-ocean-50"
                          : "text-ocean-300 hover:bg-ocean-800"
                      }`}
                      title={a.file_path}
                    >
                      {a.file_path}
                    </button>
                  </li>
                );
              })}
            </ul>
          </div>
        ))}
      </nav>

      {selected && <FileView artifact={selected} />}
    </div>
  );
}

function FileView({ artifact }: { artifact: BuildArtifact }) {
  return (
    <section className="rounded border border-ocean-800 bg-ocean-950">
      <header className="flex items-center justify-between gap-2 border-b border-ocean-800 px-2 py-1.5">
        <span className="min-w-0 truncate text-xs text-ocean-200" title={artifact.file_path}>
          {artifact.file_path}
        </span>
        <span className="shrink-0 rounded bg-ocean-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ocean-300">
          {artifact.language}
        </span>
      </header>
      <Highlight
        theme={themes.oceanicNext}
        code={artifact.content}
        language={prismLanguage(artifact.language)}
      >
        {({ className, style, tokens, getLineProps, getTokenProps }) => (
          <pre
            className={`${className} overflow-auto p-2 text-[11px] leading-relaxed`}
            style={style}
          >
            {tokens.map((line, i) => {
              const lineProps = getLineProps({ line });
              return (
                <div key={i} {...lineProps}>
                  <span className="mr-3 inline-block w-6 select-none text-right text-ocean-600">
                    {i + 1}
                  </span>
                  {line.map((token, key) => {
                    const tokenProps = getTokenProps({ token });
                    return <span key={key} {...tokenProps} />;
                  })}
                </div>
              );
            })}
          </pre>
        )}
      </Highlight>
    </section>
  );
}

// Sort artifacts into ascending-phase groups, files sorted by path within each.
function groupByPhase(
  artifacts: BuildArtifact[],
): { phase: number; files: BuildArtifact[] }[] {
  const byPhase = new Map<number, BuildArtifact[]>();
  for (const a of artifacts) {
    const list = byPhase.get(a.phase_number) ?? [];
    list.push(a);
    byPhase.set(a.phase_number, list);
  }
  return Array.from(byPhase.entries())
    .sort(([a], [b]) => a - b)
    .map(([phase, files]) => ({
      phase,
      files: [...files].sort((x, y) => x.file_path.localeCompare(y.file_path)),
    }));
}

// Prism doesn't know every backend `language` string; normalize the common ones
// and fall back to plain text so highlighting never throws on an unknown grammar.
function prismLanguage(language: string): string {
  const lang = language.toLowerCase();
  const aliases: Record<string, string> = {
    py: "python",
    js: "javascript",
    ts: "typescript",
    tsx: "tsx",
    jsx: "jsx",
    sh: "bash",
    shell: "bash",
    yml: "yaml",
    md: "markdown",
    "": "text",
  };
  return aliases[lang] ?? lang;
}
