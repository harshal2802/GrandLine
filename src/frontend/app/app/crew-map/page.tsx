import { Suspense } from "react";
import { CrewMap } from "@/components/observation-deck/CrewMap";

export default function CrewMapPage() {
  return (
    <Suspense>
      <CrewMap />
    </Suspense>
  );
}
