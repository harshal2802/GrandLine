import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ChangesPanel } from "./ChangesPanel";
import type { BuildArtifact, GitChangedFile, GitDiff } from "@/lib/types";

// Controllable mocks for the build-artifacts hook (A1) and the git-diff hooks
// (A2), same pattern as FleetSwitcher mocking useVoyages.
const artifactsResult = {
  data: undefined as BuildArtifact[] | undefined,
  isLoading: false,
  isError: false,
};
vi.mock("@/hooks/useBuildArtifacts", () => ({
  useBuildArtifacts: () => artifactsResult,
}));

const headResult = {
  data: null as string | null,
  isSuccess: false,
  isError: false,
};
const changedResult = {
  data: undefined as GitChangedFile[] | undefined,
  isLoading: false,
  isError: false,
};
const diffResult = {
  data: undefined as GitDiff | undefined,
  isLoading: false,
  isError: false,
};
vi.mock("@/hooks/useGitDiff", () => ({
  useGitHead: () => headResult,
  useChangedFiles: () => changedResult,
  useFileDiff: () => diffResult,
}));

function artifact(over: Partial<BuildArtifact> = {}): BuildArtifact {
  return {
    id: "a1",
    voyage_id: "v1",
    shipwright_run_id: "r1",
    phase_number: 1,
    file_path: "src/main.py",
    content: "print('hi')",
    language: "python",
    created_by: "shipwright",
    created_at: "2026-06-22T00:00:00Z",
    ...over,
  };
}

beforeEach(() => {
  artifactsResult.data = undefined;
  artifactsResult.isLoading = false;
  artifactsResult.isError = false;

  headResult.data = null;
  headResult.isSuccess = false;
  headResult.isError = false;

  changedResult.data = undefined;
  changedResult.isLoading = false;
  changedResult.isError = false;

  diffResult.data = undefined;
  diffResult.isLoading = false;
  diffResult.isError = false;
});

afterEach(() => {
  cleanup();
});

describe("ChangesPanel — Files mode (A1)", () => {
  it("shows a loading state", () => {
    artifactsResult.isLoading = true;
    render(<ChangesPanel voyageId="v1" />);
    expect(screen.getByText(/Charting the changes/i)).toBeInTheDocument();
  });

  it("shows an error state", () => {
    artifactsResult.isError = true;
    render(<ChangesPanel voyageId="v1" />);
    expect(screen.getByText(/Couldn't reach the changes/i)).toBeInTheDocument();
  });

  it("shows an empty state when there are no artifacts", () => {
    artifactsResult.data = [];
    render(<ChangesPanel voyageId="v1" />);
    expect(
      screen.getByText(/No changes yet — the crew hasn't built any files/i),
    ).toBeInTheDocument();
  });

  it("groups files by phase", () => {
    artifactsResult.data = [
      artifact({ id: "a1", phase_number: 1, file_path: "src/main.py" }),
      artifact({ id: "a2", phase_number: 1, file_path: "src/util.py" }),
      artifact({ id: "a3", phase_number: 2, file_path: "src/app.py" }),
    ];
    render(<ChangesPanel voyageId="v1" />);

    expect(screen.getByText("Phase 1")).toBeInTheDocument();
    expect(screen.getByText("Phase 2")).toBeInTheDocument();
    expect(screen.getAllByText("src/util.py").length).toBeGreaterThan(0);
    expect(screen.getAllByText("src/app.py").length).toBeGreaterThan(0);
  });

  it("selecting a file shows its content and language badge", () => {
    artifactsResult.data = [
      artifact({ id: "a1", file_path: "src/main.py", content: "print('main')" }),
      artifact({
        id: "a2",
        file_path: "src/other.py",
        content: "print('other')",
        language: "python",
      }),
    ];
    render(<ChangesPanel voyageId="v1" />);

    fireEvent.click(screen.getByRole("button", { name: "src/other.py" }));

    expect(screen.getByText(/'other'/)).toBeInTheDocument();
    expect(screen.getByText("python")).toBeInTheDocument();
  });
});

describe("ChangesPanel — Diff mode (A2)", () => {
  it("renders the changed-file list and a unified diff when the voyage used git", () => {
    headResult.data = "agent/shipwright/abc12345";
    headResult.isSuccess = true;
    changedResult.data = [
      { path: "src/main.py", status: "M" },
      { path: "src/new.py", status: "A" },
    ];
    diffResult.data = {
      base: "main",
      head: "agent/shipwright/abc12345",
      path: "src/main.py",
      unified: "diff --git a/src/main.py b/src/main.py\n+added line\n-removed line\n",
    };

    render(<ChangesPanel voyageId="v1" />);
    fireEvent.click(screen.getByRole("tab", { name: "Diff" }));

    // changed-file list
    expect(screen.getAllByText("src/main.py").length).toBeGreaterThan(0);
    expect(screen.getByText("src/new.py")).toBeInTheDocument();
    // unified diff content (token spans concatenate to the source)
    expect(screen.getByText(/added line/)).toBeInTheDocument();
    // base…head label
    expect(screen.getByText(/main … agent\/shipwright\/abc12345/)).toBeInTheDocument();
  });

  it("falls back to the Files (A1) view when the voyage has no git branch", () => {
    headResult.data = null;
    headResult.isSuccess = true; // settled, but no crew branch
    artifactsResult.data = [artifact({ file_path: "src/main.py" })];

    render(<ChangesPanel voyageId="v1" />);
    fireEvent.click(screen.getByRole("tab", { name: "Diff" }));

    expect(
      screen.getByText(/didn't use git — showing the built files/i),
    ).toBeInTheDocument();
    expect(screen.getAllByText("src/main.py").length).toBeGreaterThan(0);
  });

  it("falls back to the Files view when the head query errors (git absent)", () => {
    headResult.isError = true;
    artifactsResult.data = [artifact({ file_path: "src/main.py" })];

    render(<ChangesPanel voyageId="v1" />);
    fireEvent.click(screen.getByRole("tab", { name: "Diff" }));

    expect(
      screen.getByText(/didn't use git — showing the built files/i),
    ).toBeInTheDocument();
  });

  it("shows an empty diff state when the branch matches the base", () => {
    headResult.data = "agent/shipwright/abc12345";
    headResult.isSuccess = true;
    changedResult.data = [];

    render(<ChangesPanel voyageId="v1" />);
    fireEvent.click(screen.getByRole("tab", { name: "Diff" }));

    expect(screen.getByText(/No git changes/i)).toBeInTheDocument();
  });
});
