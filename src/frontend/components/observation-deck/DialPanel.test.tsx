import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { createElement, type ReactNode } from "react";
import { DialPanel } from "./DialPanel";
import type { DialConfig, DialStatus } from "@/lib/dial";
import type { CredentialStatus } from "@/lib/seaChest";

// Mock the dial API layer (config read/write + status) and the sea-chest layer.
const getDialConfig = vi.fn();
const getDialStatus = vi.fn();
const updateDialConfig = vi.fn();

vi.mock("@/lib/dial", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/dial")>();
  return {
    ...actual,
    getDialConfig: (...a: unknown[]) => getDialConfig(...a),
    getDialStatus: (...a: unknown[]) => getDialStatus(...a),
    updateDialConfig: (...a: unknown[]) => updateDialConfig(...a),
  };
});

const getSeaChest = vi.fn();
const disconnectCredential = vi.fn();
vi.mock("@/lib/seaChest", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/seaChest")>();
  return {
    ...actual,
    getSeaChest: (...a: unknown[]) => getSeaChest(...a),
    disconnectCredential: (...a: unknown[]) => disconnectCredential(...a),
  };
});

function dialConfig(over: Partial<DialConfig> = {}): DialConfig {
  return {
    id: "dc1",
    voyage_id: "v1",
    role_mapping: {
      captain: { provider: "anthropic", model: "claude-3-5-sonnet" },
      navigator: { provider: "anthropic", model: "claude-3-5-sonnet" },
      doctor: { provider: "anthropic", model: "claude-3-5-sonnet" },
      shipwright: { provider: "claude_code", model: "sonnet" },
      helmsman: { provider: "anthropic", model: "claude-3-5-sonnet" },
    },
    fallback_chain: null,
    created_at: "2026-06-22T00:00:00Z",
    updated_at: "2026-06-22T00:00:00Z",
    ...over,
  };
}

function dialStatus(): DialStatus {
  return { voyage_id: "v1", window_seconds: 60, providers: [] };
}

function credStatus(over: Partial<CredentialStatus> = {}): CredentialStatus {
  return {
    kind: "claude_code",
    connected: true,
    label: "device-login",
    created_at: "2026-06-22T00:00:00Z",
    last_used_at: null,
    ...over,
  };
}

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const Wrapper = ({ children }: { children: ReactNode }) =>
    createElement(QueryClientProvider, { client }, children);
  return render(<DialPanel voyageId="v1" />, { wrapper: Wrapper });
}

beforeEach(() => {
  getDialConfig.mockReset();
  getDialStatus.mockReset();
  updateDialConfig.mockReset();
  getSeaChest.mockReset();
  disconnectCredential.mockReset();

  getDialConfig.mockResolvedValue(dialConfig());
  getDialStatus.mockResolvedValue(dialStatus());
  updateDialConfig.mockImplementation((_id: string, body: unknown) =>
    Promise.resolve({ ...dialConfig(), ...(body as object) }),
  );
  getSeaChest.mockResolvedValue([
    credStatus({ kind: "claude_code", connected: true, label: "device-login" }),
    credStatus({ kind: "github", connected: false, label: null }),
  ]);
  disconnectCredential.mockResolvedValue(undefined);
});

afterEach(() => {
  cleanup();
});

describe("DialPanel — existing behavior", () => {
  it("renders the role→provider rows and saves role_mapping", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText("captain")).toBeInTheDocument());

    const models = screen.getAllByPlaceholderText("model");
    fireEvent.change(models[0], { target: { value: "claude-opus" } });

    fireEvent.click(screen.getByRole("button", { name: /Save/i }));

    await waitFor(() => expect(updateDialConfig).toHaveBeenCalled());
    const [, body] = updateDialConfig.mock.calls[0];
    expect(body.role_mapping.captain.model).toBe("claude-opus");
  });
});

describe("DialPanel — claude_code max_turns (C2 + C1)", () => {
  it("shows a max_turns control only for claude_code rows", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText("shipwright")).toBeInTheDocument());

    // shipwright is claude_code in the fixture → its row has a max_turns control.
    const turns = screen.getAllByLabelText(/max turns/i);
    // exactly one claude_code row in the fixture
    expect(turns).toHaveLength(1);
  });

  it("round-trips max_turns into the saved role_mapping", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText("shipwright")).toBeInTheDocument());

    const turns = screen.getByLabelText(/max turns/i);
    fireEvent.change(turns, { target: { value: "4" } });

    fireEvent.click(screen.getByRole("button", { name: /Save/i }));
    await waitFor(() => expect(updateDialConfig).toHaveBeenCalled());

    const [, body] = updateDialConfig.mock.calls[0];
    expect(body.role_mapping.shipwright.max_turns).toBe(4);
  });

  it("a stray max_turns does not block the provider+model save guard", async () => {
    // a claude_code row WITH a model is valid even with max_turns set
    renderPanel();
    await waitFor(() => expect(screen.getByText("shipwright")).toBeInTheDocument());

    const turns = screen.getByLabelText(/max turns/i);
    fireEvent.change(turns, { target: { value: "3" } });

    const save = screen.getByRole("button", { name: /Save/i });
    expect(save).not.toBeDisabled();
  });
});

describe("DialPanel — editable fallback chains (C2)", () => {
  it("adds a fallback entry and saves fallback_chain", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText("captain")).toBeInTheDocument());

    // Add a fallback entry to the captain role.
    const addButtons = screen.getAllByRole("button", { name: /add fallback/i });
    fireEvent.click(addButtons[0]);

    fireEvent.click(screen.getByRole("button", { name: /Save/i }));
    await waitFor(() => expect(updateDialConfig).toHaveBeenCalled());

    const [, body] = updateDialConfig.mock.calls[0];
    expect(body.fallback_chain).toBeTruthy();
    const captainChain = body.fallback_chain.captain;
    expect(Array.isArray(captainChain)).toBe(true);
    expect(captainChain.length).toBeGreaterThan(0);
    // normalized to object form
    expect(captainChain[0]).toHaveProperty("provider");
  });

  it("removes a seeded fallback entry", async () => {
    getDialConfig.mockResolvedValue(
      dialConfig({
        fallback_chain: { captain: [{ provider: "openai", model: "gpt-4o" }] },
      }),
    );
    renderPanel();
    await waitFor(() => expect(screen.getByText("captain")).toBeInTheDocument());

    // The seeded entry renders as an editable provider select + model input.
    const modelInput = screen.getByLabelText(/captain fallback 1 model/i) as HTMLInputElement;
    expect(modelInput.value).toBe("gpt-4o");
    fireEvent.click(screen.getByRole("button", { name: /remove fallback 1 from captain/i }));

    fireEvent.click(screen.getByRole("button", { name: /Save/i }));
    await waitFor(() => expect(updateDialConfig).toHaveBeenCalled());

    const [, body] = updateDialConfig.mock.calls[0];
    expect(body.fallback_chain.captain).toEqual([]);
  });
});

describe("DialPanel — Sea Chest connection status (C2)", () => {
  it("renders Connected / Not connected from sea-chest data", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText(/device-login/)).toBeInTheDocument());

    expect(screen.getByText("Connected")).toBeInTheDocument();
    expect(screen.getByText("Not connected")).toBeInTheDocument();
  });

  it("Disconnect calls the DELETE for that kind", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText(/device-login/)).toBeInTheDocument());

    fireEvent.click(screen.getByRole("button", { name: /disconnect/i }));
    await waitFor(() => expect(disconnectCredential).toHaveBeenCalledWith("claude_code"));
  });

  it("shows a disabled 'coming soon' Connect affordance for a not-connected kind", async () => {
    renderPanel();
    await waitFor(() => expect(screen.getByText(/Not connected/i)).toBeInTheDocument());

    const connect = screen.getByRole("button", { name: "Connect" });
    expect(connect).toBeDisabled();
    expect(screen.getByText(/coming soon/i)).toBeInTheDocument();
  });
});
