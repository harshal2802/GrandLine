// Real git-diff hooks over the Phase A2 endpoints
// (GET /voyages/{id}/git/changed-files|diff|branches). The deck's Changes view
// uses these for its Diff mode; when a voyage never used git (no crew branch) or
// a call fails, the view falls back to the A1 artifacts browser.
//
// The crew works on an `agent/<role>/<voyage>` branch off `main`. We DISCOVER
// that head branch from the existing /git/branches endpoint (no extra plumbing
// through the component) and gate the diff reads on having found one — a voyage
// that never cloned a repo returns no such branch (or errors), which is the
// signal to fall back to A1.

"use client";

import { useQuery } from "@tanstack/react-query";
import { apiFetch } from "@/lib/api";
import type { GitChangedFile, GitDiff } from "@/lib/types";

const BASE_BRANCH = "main";

type GitBranchInfo = { name: string; is_current: boolean };

// Pick the crew's working branch: the first `agent/*` branch, else the current
// branch if it isn't the base, else null (nothing to diff → fall back to A1).
export function pickHeadBranch(branches: GitBranchInfo[]): string | null {
  const agent = branches.find((b) => b.name.startsWith("agent/"));
  if (agent) return agent.name;
  const current = branches.find((b) => b.is_current);
  if (current && current.name !== BASE_BRANCH) return current.name;
  return null;
}

// Discover the head branch for a voyage. `data` is `null` when the voyage has no
// crew branch (no git); `isError` when the repo was never cloned / git is absent.
export function useGitHead(voyageId: string | null) {
  return useQuery<string | null>({
    queryKey: ["git-head", voyageId],
    queryFn: async () => {
      const branches = await apiFetch<GitBranchInfo[]>(
        `/voyages/${voyageId}/git/branches`,
      );
      return pickHeadBranch(branches);
    },
    enabled: !!voyageId,
    retry: false,
    staleTime: 30_000,
  });
}

export function useChangedFiles(voyageId: string | null, head: string | null) {
  return useQuery<GitChangedFile[]>({
    queryKey: ["git-changed-files", voyageId, head],
    queryFn: async () => {
      const params = new URLSearchParams({ base: BASE_BRANCH, head: head as string });
      return apiFetch<GitChangedFile[]>(
        `/voyages/${voyageId}/git/changed-files?${params.toString()}`,
      );
    },
    enabled: !!voyageId && !!head,
    retry: false,
    staleTime: 30_000,
  });
}

export function useFileDiff(
  voyageId: string | null,
  head: string | null,
  path: string | null,
) {
  return useQuery<GitDiff>({
    queryKey: ["git-diff", voyageId, head, path],
    queryFn: async () => {
      const params = new URLSearchParams({ base: BASE_BRANCH, head: head as string });
      if (path) params.set("path", path);
      return apiFetch<GitDiff>(
        `/voyages/${voyageId}/git/diff?${params.toString()}`,
      );
    },
    enabled: !!voyageId && !!head,
    retry: false,
    staleTime: 30_000,
  });
}
