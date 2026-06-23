// Preview API client + types (mirrors app/services/preview_service.py PreviewInfo —
// Phases B0/B1/B2). "Preview" runs the crew's built app as a long-running process
// INSIDE the user's Cabin and exposes a real reachable URL + captured logs. The API
// carries NO secret — only {preview_id, url, status}; logs are app stdout/stderr only.
//
// B1 adds a live SSE log stream at GET /voyages/{id}/preview/logs/stream; the
// EventSource client for it lives in hooks/usePreviewLogs.ts.

import { apiFetch } from "@/lib/api";

// Mirrors app/cabin/backend.py ServiceStatus.
export type PreviewStatus = "starting" | "running" | "stopped" | "failed";

// Secret-free handle, exactly as the backend returns it. There is NO secret field.
export interface PreviewInfo {
  preview_id: string;
  url: string;
  status: PreviewStatus;
}

export function startPreview(voyageId: string): Promise<PreviewInfo> {
  return apiFetch<PreviewInfo>(`/voyages/${voyageId}/preview`, { method: "POST" });
}

export function getPreview(voyageId: string): Promise<PreviewInfo> {
  return apiFetch<PreviewInfo>(`/voyages/${voyageId}/preview`);
}

export function stopPreview(voyageId: string): Promise<void> {
  return apiFetch<void>(`/voyages/${voyageId}/preview`, { method: "DELETE" });
}
