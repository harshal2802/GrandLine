import { Suspense } from "react";
import { PreviewPanel } from "@/components/observation-deck/PreviewPanel";

export default function PreviewPage() {
  return (
    <Suspense>
      <PreviewPanel />
    </Suspense>
  );
}
