// Shared empty / loading / error surface for every view.

export function EmptyState({
  title,
  hint,
  icon = "⚓",
}: {
  title: string;
  hint?: string;
  icon?: string;
}) {
  return (
    <div className="flex h-full min-h-64 flex-col items-center justify-center gap-2 text-center text-ocean-400">
      <span className="text-4xl" aria-hidden>
        {icon}
      </span>
      <p className="text-sm font-medium text-ocean-300">{title}</p>
      {hint && <p className="max-w-sm text-xs text-ocean-500">{hint}</p>}
    </div>
  );
}
