import { Suspense } from "react";
import { ShipsLog } from "@/components/observation-deck/ShipsLog";

export default function ShipsLogPage() {
  return (
    <Suspense>
      <ShipsLog />
    </Suspense>
  );
}
