import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { FleetSwitcher } from "./FleetSwitcher";
import { useUiStore } from "@/stores/ui";
import { useVoyageStore } from "@/stores/voyage";
import { useDeckStateStore } from "@/stores/deckState";
import type { VoyageListItem } from "@/lib/types";

const push = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push }),
}));

// Controllable mock for the voyage list hook.
const voyagesResult = {
  data: { pages: [{ items: [] as VoyageListItem[] }] },
  isLoading: false,
  error: null as Error | null,
};
vi.mock("@/hooks/useVoyages", () => ({
  useVoyages: () => voyagesResult,
}));

function voyage(id: string, title: string): VoyageListItem {
  return {
    id,
    title,
    description: null,
    status: "BUILDING",
    target_repo: null,
    phase_status: {},
    created_at: "2026-06-22T00:00:00Z",
    updated_at: "2026-06-22T00:00:00Z",
  };
}

beforeEach(() => {
  push.mockClear();
  localStorage.clear();
  useDeckStateStore.getState().reset();
  useVoyageStore.getState().reset();
  voyagesResult.data = { pages: [{ items: [] }] };
  voyagesResult.isLoading = false;
  voyagesResult.error = null;
  useUiStore.getState().setFleet(true);
});

afterEach(() => {
  cleanup();
  useUiStore.getState().setFleet(false);
  vi.clearAllMocks();
});

describe("FleetSwitcher", () => {
  it("renders nothing when closed", () => {
    useUiStore.getState().setFleet(false);
    const { container } = render(<FleetSwitcher />);
    expect(container.firstChild).toBeNull();
  });

  it("lists voyages with title + status when open", () => {
    voyagesResult.data = {
      pages: [{ items: [voyage("v1", "Find the One Piece"), voyage("v2", "Bugfix run")] }],
    };
    render(<FleetSwitcher />);
    expect(screen.getByText("Find the One Piece")).toBeInTheDocument();
    expect(screen.getByText("Bugfix run")).toBeInTheDocument();
    expect(screen.getAllByText("BUILDING").length).toBe(2);
  });

  it("switching a voyage calls selectVoyage and restores its lastView", () => {
    voyagesResult.data = { pages: [{ items: [voyage("v1", "Find the One Piece")] }] };
    // v1 was last on the Ship's Log.
    useDeckStateStore.getState().setLastView("v1", "ships-log");
    const selectSpy = vi.spyOn(useVoyageStore.getState(), "selectVoyage");

    render(<FleetSwitcher />);
    fireEvent.click(screen.getByText("Find the One Piece"));

    expect(selectSpy).toHaveBeenCalledWith("v1");
    expect(push).toHaveBeenCalledWith("/app/ships-log?voyage=v1");
    // Selecting closes the switcher.
    expect(useUiStore.getState().fleetOpen).toBe(false);
  });

  it("defaults to sea-chart for a never-visited voyage", () => {
    voyagesResult.data = { pages: [{ items: [voyage("v9", "Fresh voyage")] }] };
    render(<FleetSwitcher />);
    fireEvent.click(screen.getByText("Fresh voyage"));
    expect(push).toHaveBeenCalledWith("/app/sea-chart?voyage=v9");
  });

  it("filters by title", () => {
    voyagesResult.data = {
      pages: [{ items: [voyage("v1", "Find the One Piece"), voyage("v2", "Bugfix run")] }],
    };
    render(<FleetSwitcher />);
    fireEvent.change(screen.getByLabelText("Filter voyages"), {
      target: { value: "bug" },
    });
    expect(screen.queryByText("Find the One Piece")).not.toBeInTheDocument();
    expect(screen.getByText("Bugfix run")).toBeInTheDocument();
  });

  it("shows a loading state", () => {
    voyagesResult.isLoading = true;
    render(<FleetSwitcher />);
    expect(screen.getByText(/Hailing the fleet/i)).toBeInTheDocument();
  });

  it("shows an error state", () => {
    voyagesResult.error = new Error("boom");
    render(<FleetSwitcher />);
    expect(screen.getByText(/Couldn't reach the fleet/i)).toBeInTheDocument();
  });

  it("shows an empty state when the fleet is empty", () => {
    voyagesResult.data = { pages: [{ items: [] }] };
    render(<FleetSwitcher />);
    expect(screen.getByText(/No voyages yet/i)).toBeInTheDocument();
  });
});
