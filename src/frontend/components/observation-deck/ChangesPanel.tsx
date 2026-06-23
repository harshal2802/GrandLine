"use client";

import { useMemo, useState } from "react";
import { Highlight, themes } from "prism-react-renderer";
import { useBuildArtifacts } from "@/hooks/useBuildArtifacts";
import { useChangedFiles, useFileDiff, useGitHead } from "@/hooks/useGitDiff";
import type { BuildArtifact } from "@/lib/types";

interface ChangesPanelProps {
  voyageId: string | null;
}

type Mode = "files" | "diff";

// Phase A1 + A2 — the "Changes" view. A "Files" mode lists every file the crew
// built (BuildArtifact{file_path, content, language, phase_number}) grouped by
// phase with syntax-highlighted content — the always-available, no-git browser.
// A "Diff" mode (A2) shows REAL git diffs (changed-file list + unified diff,
// base ↔ the crew's branch) when the voyage actually used git. When no crew
// branch exists / the diff calls fail, Diff mode falls back to the Files view.
export function ChangesPanel({ voyageId }: ChangesPanelProps) {
  const [mode, setMode] = useState<Mode>("files");

  // A2 git head — drives whether Diff mode has anything to show.
  const headQuery = useGitHead(voyageId);
  const head = headQuery.data ?? null;
  // No git iff the head query settled with no crew branch, or it errored
  // (repo never cloned / git absent). Either way → fall back to A1.
  const hasGit = headQuery.isSuccess && head !== null;
  const noGit = (headQuery.isSuccess && head === null) || headQuery.isError;

  return (
    <div className="space-y-3">
      <div
        role="tablist"
        aria-label="Changes mode"
        className="flex gap-1 rounded bg-ocean-900 p-0.5 text-xs"
      >
        <ModeTab
          label="Files"
          active={mode === "files"}
          onClick={() => setMode("files")}
        />
        <ModeTab
          label="Diff"
          active={mode === "diff"}
          onClick={() => setMode("diff")}
        />
      </div>

      {mode === "diff" && hasGit ? (
        <DiffView voyageId={voyageId} head={head} />
      ) : (
        <FilesView voyageId={voyageId} showFallbackNote={mode === "diff" && noGit} />
      )}
    </div>
  );
}

function ModeTab({
  label,
  active,
  onClick,
}: {
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      role="tab"
      aria-selected={active}
      onClick={onClick}
      className={`flex-1 rounded px-2 py-1 ${
        active ? "bg-ocean-700 text-ocean-50" : "text-ocean-300 hover:bg-ocean-800"
      }`}
    >
      {label}
    </button>
  );
}

// ---- A1: artifact-based file browser (also the Diff-mode fallback) ----

function FilesView({
  voyageId,
  showFallbackNote,
}: {
  voyageId: string | null;
  showFallbackNote: boolean;
}) {
  const query = useBuildArtifacts(voyageId);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const artifacts = useMemo(() => query.data ?? [], [query.data]);
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
      {showFallbackNote && (
        <p className="text-[11px] text-ocean-500">
          This voyage didn&apos;t use git — showing the built files instead.
        </p>
      )}
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

// ---- A2: real git diffs ----

function DiffView({
  voyageId,
  head,
}: {
  voyageId: string | null;
  head: string;
}) {
  const filesQuery = useChangedFiles(voyageId, head);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);

  const files = useMemo(() => filesQuery.data ?? [], [filesQuery.data]);
  const selected = files.find((f) => f.path === selectedPath) ?? files[0] ?? null;

  const diffQuery = useFileDiff(voyageId, head, selected?.path ?? null);

  if (filesQuery.isLoading) {
    return <p className="text-xs text-ocean-400">Charting the diff…</p>;
  }
  // A failed changed-files read (e.g. git missing) → fall back to A1.
  if (filesQuery.isError) {
    return (
      <FilesView
        voyageId={voyageId}
        showFallbackNote
      />
    );
  }
  if (files.length === 0) {
    return (
      <p className="text-xs text-ocean-400">
        No git changes — this branch matches the base.
      </p>
    );
  }

  return (
    <div className="space-y-3">
      <p className="truncate text-[11px] text-ocean-500" title={head}>
        main … {head}
      </p>
      <nav aria-label="Changed files" className="space-y-0.5">
        <ul className="space-y-0.5">
          {files.map((f) => {
            const isActive = selected?.path === f.path;
            return (
              <li key={f.path}>
                <button
                  onClick={() => setSelectedPath(f.path)}
                  aria-current={isActive ? "true" : undefined}
                  className={`flex w-full items-center gap-2 truncate rounded px-2 py-1 text-left text-xs ${
                    isActive
                      ? "bg-ocean-700 text-ocean-50"
                      : "text-ocean-300 hover:bg-ocean-800"
                  }`}
                  title={f.path}
                >
                  <StatusBadge status={f.status} />
                  <span className="min-w-0 truncate">{f.path}</span>
                </button>
              </li>
            );
          })}
        </ul>
      </nav>

      {selected && (
        <DiffView_File path={selected.path} query={diffQuery} />
      )}
    </div>
  );
}

function StatusBadge({ status }: { status: string }) {
  const letter = status.charAt(0).toUpperCase();
  const color =
    letter === "A"
      ? "bg-emerald-900 text-emerald-300"
      : letter === "D"
        ? "bg-rose-900 text-rose-300"
        : letter === "R"
          ? "bg-amber-900 text-amber-300"
          : "bg-ocean-800 text-ocean-300";
  return (
    <span
      className={`shrink-0 rounded px-1 py-0.5 text-[9px] font-medium uppercase ${color}`}
    >
      {letter}
    </span>
  );
}

function DiffView_File({
  path,
  query,
}: {
  path: string;
  query: ReturnType<typeof useFileDiff>;
}) {
  return (
    <section className="rounded border border-ocean-800 bg-ocean-950">
      <header className="flex items-center justify-between gap-2 border-b border-ocean-800 px-2 py-1.5">
        <span className="min-w-0 truncate text-xs text-ocean-200" title={path}>
          {path}
        </span>
        <span className="shrink-0 rounded bg-ocean-800 px-1.5 py-0.5 text-[10px] uppercase tracking-wide text-ocean-300">
          diff
        </span>
      </header>
      {query.isLoading ? (
        <p className="p-2 text-xs text-ocean-400">Charting the diff…</p>
      ) : query.isError ? (
        <p className="p-2 text-xs text-rose-400">
          Couldn&apos;t load this file&apos;s diff.
        </p>
      ) : !query.data?.unified.trim() ? (
        <p className="p-2 text-xs text-ocean-400">No changes in this file.</p>
      ) : (
        <UnifiedDiff unified={query.data.unified} />
      )}
    </section>
  );
}

// Render a unified diff with prism-react-renderer's `diff` grammar so added /
// removed lines are colored. (Reuses the A1 highlighter — no new diff lib.)
function UnifiedDiff({ unified }: { unified: string }) {
  return (
    <Highlight theme={themes.oceanicNext} code={unified} language="diff">
      {({ className, style, tokens, getLineProps, getTokenProps }) => (
        <pre
          className={`${className} overflow-auto p-2 text-[11px] leading-relaxed`}
          style={style}
        >
          {tokens.map((line, i) => {
            const lineProps = getLineProps({ line });
            const first = line[0]?.content ?? "";
            const tone = first.startsWith("+")
              ? "bg-emerald-950/60"
              : first.startsWith("-")
                ? "bg-rose-950/60"
                : "";
            return (
              <div key={i} {...lineProps} className={`${lineProps.className ?? ""} ${tone}`}>
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
