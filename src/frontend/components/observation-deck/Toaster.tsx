"use client";

import { useToastStore } from "@/stores/toast";

const TONE_CLASS: Record<string, string> = {
  info: "border-ocean-600 bg-ocean-800",
  warn: "border-amber-600 bg-amber-900/70",
  success: "border-emerald-600 bg-emerald-900/70",
  error: "border-rose-600 bg-rose-900/70",
};

export function Toaster() {
  const toasts = useToastStore((s) => s.toasts);
  const dismiss = useToastStore((s) => s.dismiss);

  if (toasts.length === 0) return null;

  return (
    <div
      className="pointer-events-none fixed bottom-4 right-4 z-[60] flex w-80 max-w-[calc(100vw-2rem)] flex-col gap-2"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          role="status"
          className={`pointer-events-auto rounded-lg border px-3 py-2 text-sm shadow-lg ${
            TONE_CLASS[t.tone] ?? TONE_CLASS.info
          }`}
        >
          <div className="flex items-start justify-between gap-2">
            <p className="font-medium text-ocean-50">{t.title}</p>
            <button
              onClick={() => dismiss(t.id)}
              className="text-ocean-300 hover:text-ocean-100"
              aria-label="Dismiss notification"
            >
              ✕
            </button>
          </div>
          {t.body && <p className="mt-0.5 text-xs text-ocean-200">{t.body}</p>}
        </div>
      ))}
    </div>
  );
}
