"use client";

import React, { useState, useEffect, useCallback } from "react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { X, AlertTriangle } from "lucide-react";

// Helper to format the countdown
function formatCET(epochSec?: number | null) {
  if (!epochSec) return "";
  // CET fixed +1: add 60 minutes to UTC and format HH:mm
  const date = new Date((epochSec + 60 * 60) * 1000);
  const hh = String(date.getUTCHours()).padStart(2, "0");
  const mm = String(date.getUTCMinutes()).padStart(2, "0");
  return `${hh}:${mm} CET`;
}

function composeCountdown(base: string, untilEpoch?: number | null, resetEpoch?: number | null) {
  const now = Math.floor(Date.now() / 1000);
  const secs = Math.max(0, (untilEpoch ?? now) - now);
  const resets = formatCET(resetEpoch ?? untilEpoch ?? null);
  const parts: string[] = [];
  parts.push(base);
  parts.push(`Try again in ${secs}s`);
  if (resets) parts.push(`Resets at ${resets}`);
  return parts.join(". ") + ".";
}

export function RateLimitAlert({ message, onDismiss }: { message: any; onDismiss: (id: string) => void }) {
  const { id, title, until, reset } = message;
  const [description, setDescription] = useState("");

  useEffect(() => {
    const intervalId = setInterval(() => {
      const now = Math.floor(Date.now() / 1000);
      if (now >= until) {
        onDismiss(id);
        clearInterval(intervalId);
      } else {
        setDescription(composeCountdown(title, until, reset));
      }
    }, 1000);

    // Initial description
    setDescription(composeCountdown(title, until, reset));

    return () => clearInterval(intervalId);
  }, [id, title, until, reset, onDismiss]);

  return (
    <div key={id} className="relative">
      <Alert variant="warning">
        <AlertTriangle className="h-5 w-5" />
        <div>
          {title && <AlertTitle className="text-sm font-medium">{title}</AlertTitle>}
          {description && <AlertDescription className="text-sm">{description}</AlertDescription>}
        </div>
        <button
          type="button"
          className="absolute right-2 top-2 rounded-md p-1 text-foreground/60 hover:bg-muted focus:outline-none focus:ring-2"
          aria-label="Dismiss"
          onClick={() => onDismiss(id)}
        >
          <X className="h-4 w-4" />
        </button>
      </Alert>
    </div>
  );
}
