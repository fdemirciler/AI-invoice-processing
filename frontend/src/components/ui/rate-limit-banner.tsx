"use client";

import React, { useState, useEffect } from "react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { X, AlertTriangle } from "lucide-react";
import type { RateLimitMessage } from "@/hooks/use-rate-limit";

// Helper to format the countdown
function formatCET(epochSec?: number | null) {
  if (!epochSec) return "";
  // CET fixed +1: add 60 minutes to UTC and format HH:mm
  const date = new Date((epochSec + 60 * 60) * 1000);
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm} CET`;
}

function composeCountdown(base: string, retryAfterSec?: number, resetEpoch?: number) {
  const now = Math.floor(Date.now() / 1000);
  const until = now + (retryAfterSec || 0);
  const secs = Math.max(0, until - now);
  const resets = formatCET(resetEpoch);
  
  const parts: string[] = [];
  parts.push(base);
  if (secs > 0) parts.push(`Try again in ${secs}s`);
  if (resets) parts.push(`Resets at ${resets}`);
  return parts.join(". ") + ".";
}

interface RateLimitBannerProps {
  message: RateLimitMessage;
  onDismiss: () => void;
}

export function RateLimitBanner({ message, onDismiss }: RateLimitBannerProps) {
  const [description, setDescription] = useState("");
  const [isExpired, setIsExpired] = useState(false);

  useEffect(() => {
    const updateCountdown = () => {
      const now = Math.floor(Date.now() / 1000);
      const until = now + (message.retryAfterSec || 0);
      
      if (now >= until) {
        setIsExpired(true);
        return;
      }
      
      setDescription(composeCountdown(message.title, message.retryAfterSec, message.resetEpoch));
    };

    // Initial update
    updateCountdown();
    
    // Update every second
    const intervalId = setInterval(updateCountdown, 1000);

    return () => clearInterval(intervalId);
  }, [message.title, message.retryAfterSec, message.resetEpoch]);

  // Auto-dismiss when expired
  useEffect(() => {
    if (isExpired) {
      onDismiss();
    }
  }, [isExpired, onDismiss]);

  return (
    <Alert variant="warning" className="mb-4">
      <AlertTriangle className="h-5 w-5" />
      <div>
        <AlertTitle className="text-sm font-medium">{message.title}</AlertTitle>
        {description && <AlertDescription className="text-sm">{description}</AlertDescription>}
      </div>
      <button
        type="button"
        className="absolute right-2 top-2 rounded-md p-1 text-foreground/60 hover:bg-muted focus:outline-none focus:ring-2"
        aria-label="Dismiss"
        onClick={onDismiss}
      >
        <X className="h-4 w-4" />
      </button>
    </Alert>
  );
}
