import { describe, expect, it } from "vitest";
import { isEditableTarget, shouldIgnoreShortcut } from "@/lib/shortcuts";

function el(tag: string, attrs: Record<string, string> = {}): Element {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
  return node;
}

describe("isEditableTarget (P14)", () => {
  it("treats inputs/textareas/selects/sliders/contenteditable as editable", () => {
    expect(isEditableTarget(el("INPUT"))).toBe(true);
    expect(isEditableTarget(el("TEXTAREA"))).toBe(true);
    expect(isEditableTarget(el("DIV", { role: "slider" }))).toBe(true);
    const ce = el("DIV") as HTMLElement;
    Object.defineProperty(ce, "isContentEditable", { value: true });
    expect(isEditableTarget(ce)).toBe(true);
  });
  it("treats buttons/divs as non-editable", () => {
    expect(isEditableTarget(el("BUTTON"))).toBe(false);
    expect(isEditableTarget(el("DIV"))).toBe(false);
  });
});

describe("shouldIgnoreShortcut (P14)", () => {
  it("ignores '/' typed in an input", () => {
    expect(shouldIgnoreShortcut({ key: "/" }, el("INPUT"))).toBe(true);
  });
  it("does NOT ignore Esc in an input", () => {
    expect(shouldIgnoreShortcut({ key: "Escape" }, el("INPUT"))).toBe(false);
  });
  it("does NOT ignore Cmd-K in an input", () => {
    expect(shouldIgnoreShortcut({ key: "k", metaKey: true }, el("INPUT"))).toBe(false);
  });
  it("honors plain shortcuts outside editable controls", () => {
    expect(shouldIgnoreShortcut({ key: "g" }, el("BUTTON"))).toBe(false);
  });
});
