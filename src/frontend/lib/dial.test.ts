import { describe, expect, it } from "vitest";
import { DIAL_PROVIDERS, fallbackLabel } from "@/lib/dial";

describe("fallbackLabel", () => {
  it("renders a bare provider string", () => {
    expect(fallbackLabel("openai")).toBe("openai");
  });
  it("renders provider/model for an object entry", () => {
    expect(fallbackLabel({ provider: "openai", model: "gpt-4o" })).toBe("openai/gpt-4o");
  });
  it("renders just the provider when an object omits the model", () => {
    expect(fallbackLabel({ provider: "ollama" })).toBe("ollama");
  });
});

describe("DIAL_PROVIDERS", () => {
  it("matches the backend supported provider list", () => {
    expect([...DIAL_PROVIDERS]).toEqual(["anthropic", "openai", "ollama", "claude_code"]);
  });
});
