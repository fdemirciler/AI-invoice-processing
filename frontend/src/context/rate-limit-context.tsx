"use client";

import { createContext, useContext } from "react";
import { useRateLimit } from "@/hooks/use-rate-limit";

const RateLimitContext = createContext<ReturnType<typeof useRateLimit> | null>(null);

export function RateLimitProvider({ children }: { children: React.ReactNode }) {
  const state = useRateLimit();
  return (
    <RateLimitContext.Provider value={state}>
      {children}
    </RateLimitContext.Provider>
  );
}

export function useRateLimitContext() {
  const ctx = useContext(RateLimitContext);
  if (!ctx) throw new Error("useRateLimitContext must be used inside RateLimitProvider");
  return ctx;
}
