"use client";

import { useState, useCallback } from "react";

export interface RateLimitMessage {
  title: string;
  description?: string;
  resetEpoch?: number;
  retryAfterSec?: number;
}

export function useRateLimit() {
  const [message, setMessage] = useState<RateLimitMessage | null>(null);

  const showRateLimit = useCallback((msg: RateLimitMessage) => {
    setMessage(msg);
  }, []);

  const clearRateLimit = useCallback(() => {
    setMessage(null);
  }, []);

  return { message, showRateLimit, clearRateLimit };
}
