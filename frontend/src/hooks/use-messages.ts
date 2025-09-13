"use client";

import * as React from "react";
import { useToast as useToastBase, toast as baseToast } from "@/hooks/use-toast";

// Keep TOAST_LIMIT=3 (configured in use-toast.ts)
// Throttle identical messages within this window (ms)
const THROTTLE_MS = 2000;

// fingerprint => lastShownEpochMs
const lastShown = new Map<string, number>();

function fingerprint(input: { variant?: any; title?: React.ReactNode; description?: React.ReactNode }) {
  const v = String(input.variant ?? "default");
  const t = typeof input.title === "string" ? input.title : JSON.stringify(input.title ?? "");
  const d = typeof input.description === "string" ? input.description : JSON.stringify(input.description ?? "");
  return `${v}|${t}|${d}`;
}

function throttledToast(opts: any) {
  const now = Date.now();
  const fp = fingerprint(opts);
  const last = lastShown.get(fp) ?? 0;
  if (now - last < THROTTLE_MS) {
    return { id: "throttled", dismiss: () => {}, update: () => {} };
  }
  lastShown.set(fp, now);

  // Default duration 5000 for non-destructive messages if not provided
  const isError = opts?.variant === "destructive";
  const duration = typeof opts?.duration === "number" ? opts.duration : (isError ? undefined : 5000);
  return baseToast({ ...opts, duration });
}

export function useMessages() {
  const state = useToastBase();
  return React.useMemo(() => ({ ...state, toast: throttledToast }), [state]);
}

export { throttledToast as toast };
