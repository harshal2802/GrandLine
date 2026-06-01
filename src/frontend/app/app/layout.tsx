import { Suspense } from "react";
import { Providers } from "@/components/Providers";
import { DeckShell } from "@/components/observation-deck/DeckShell";

export default function AppLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Providers>
      <Suspense fallback={<div className="p-6 text-ocean-400">Loading deck…</div>}>
        <DeckShell>{children}</DeckShell>
      </Suspense>
    </Providers>
  );
}
