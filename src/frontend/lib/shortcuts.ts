// Keyboard-shortcut helpers (CONTRACTS P14). Editable-focus guard: ignore
// shortcuts when focus is in a text-editing control, EXCEPT for the universal
// Esc and the palette toggle (Cmd/Ctrl-K), which are always honored.

const EDITABLE_TAGS = new Set(["INPUT", "TEXTAREA", "SELECT"]);

export function isEditableTarget(el: Element | null): boolean {
  if (!el) return false;
  if (EDITABLE_TAGS.has(el.tagName)) return true;
  if ((el as HTMLElement).isContentEditable) return true;
  if (el.getAttribute("role") === "slider") return true;
  return false;
}

// Always-honored regardless of focus (P14).
export function isAlwaysHonored(e: {
  key: string;
  metaKey?: boolean;
  ctrlKey?: boolean;
}): boolean {
  if (e.key === "Escape") return true;
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") return true;
  return false;
}

export function shouldIgnoreShortcut(
  e: { key: string; metaKey?: boolean; ctrlKey?: boolean },
  activeEl: Element | null,
): boolean {
  if (isAlwaysHonored(e)) return false;
  return isEditableTarget(activeEl);
}
