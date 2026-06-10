// Minimal toast store (Zustand). Transient notifications surfaced bottom-right
// by <Toaster />. Used for Dial System failover alerts (#54).

import { create } from "zustand";

export type ToastTone = "info" | "warn" | "success" | "error";

export type Toast = {
  id: string;
  title: string;
  body?: string;
  tone: ToastTone;
};

const AUTO_DISMISS_MS = 6000;

type ToastState = {
  toasts: Toast[];
  push: (toast: Omit<Toast, "id">) => string;
  dismiss: (id: string) => void;
};

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  push: (toast) => {
    const id = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
    set((s) => ({ toasts: [...s.toasts, { ...toast, id }] }));
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, AUTO_DISMISS_MS);
    return id;
  },
  dismiss: (id) => set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) })),
}));
