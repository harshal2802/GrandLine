import { redirect } from "next/navigation";

// /app → default to the Sea Chart view (Decision 3). Voyage selection rides in
// the ?voyage=<id> query param, preserved by the deck nav.
export default function AppIndex() {
  redirect("/app/sea-chart");
}
