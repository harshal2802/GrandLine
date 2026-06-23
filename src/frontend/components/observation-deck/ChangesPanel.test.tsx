import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { ChangesPanel } from "./ChangesPanel";
import type { BuildArtifact } from "@/lib/types";

// Controllable mock for the build-artifacts hook (same pattern as FleetSwitcher
// mocking useVoyages).
const result = {
  data: undefined as BuildArtifact[] | undefined,
  isLoading: false,
  isError: false,
};
vi.mock("@/hooks/useBuildArtifacts", () => ({
  useBuildArtifacts: () => result,
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
  result.data = undefined;
  result.isLoading = false;
  result.isError = false;
});

afterEach(() => {
  cleanup();
});

describe("ChangesPanel", () => {
  it("shows a loading state", () => {
    result.isLoading = true;
    render(<ChangesPanel voyageId="v1" />);
    expect(screen.getByText(/Charting the changes/i)).toBeInTheDocument();
  });

  it("shows an error state", () => {
    result.isError = true;
    render(<ChangesPanel voyageId="v1" />);
    expect(screen.getByText(/Couldn't reach the changes/i)).toBeInTheDocument();
  });

  it("shows an empty state when there are no artifacts", () => {
    result.data = [];
    render(<ChangesPanel voyageId="v1" />);
    expect(
      screen.getByText(/No changes yet — the crew hasn't built any files/i),
    ).toBeInTheDocument();
  });

  it("groups files by phase", () => {
    result.data = [
      artifact({ id: "a1", phase_number: 1, file_path: "src/main.py" }),
      artifact({ id: "a2", phase_number: 1, file_path: "src/util.py" }),
      artifact({ id: "a3", phase_number: 2, file_path: "src/app.py" }),
    ];
    render(<ChangesPanel voyageId="v1" />);

    expect(screen.getByText("Phase 1")).toBeInTheDocument();
    expect(screen.getByText("Phase 2")).toBeInTheDocument();
    // file_path appears in the list button and the file header — at least once.
    expect(screen.getAllByText("src/util.py").length).toBeGreaterThan(0);
    expect(screen.getAllByText("src/app.py").length).toBeGreaterThan(0);
  });

  it("selecting a file shows its content and language badge", () => {
    result.data = [
      artifact({ id: "a1", file_path: "src/main.py", content: "print('main')" }),
      artifact({
        id: "a2",
        file_path: "src/other.py",
        content: "print('other')",
        language: "python",
      }),
    ];
    render(<ChangesPanel voyageId="v1" />);

    // Click the second file's list button.
    fireEvent.click(screen.getByRole("button", { name: "src/other.py" }));

    // Its content is rendered (token spans concatenate to the source).
    expect(screen.getByText(/'other'/)).toBeInTheDocument();
    expect(screen.getByText("python")).toBeInTheDocument();
  });
});
