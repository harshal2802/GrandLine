"use client";

import { useEffect } from "react";

// Route-segment error boundary for the Observation Deck. Without this, any
// render/data error inside /app crashes to a blank screen.
export default function DeckError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  useEffect(() => {
    console.error("Observation Deck error:", error);
  }, [error]);

  return (
    <div className="flex min-h-[50vh] flex-col items-center justify-center gap-4 p-6 text-center">
      <h2 className="text-lg font-semibold text-ocean-100">
        The deck hit rough waters
      </h2>
      <p className="max-w-md text-sm text-ocean-400">
        Something went wrong while rendering the Observation Deck. Your voyage
        is still running — try reloading the view.
      </p>
      <button
        type="button"
        onClick={reset}
        className="rounded-md border border-ocean-500 px-4 py-2 text-sm text-ocean-100 hover:bg-ocean-800"
      >
        Try again
      </button>
    </div>
  );
}
