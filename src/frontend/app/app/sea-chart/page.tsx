import { Suspense } from "react";
import { SeaChart } from "@/components/observation-deck/SeaChart";

export default function SeaChartPage() {
  return (
    <Suspense>
      <SeaChart />
    </Suspense>
  );
}
