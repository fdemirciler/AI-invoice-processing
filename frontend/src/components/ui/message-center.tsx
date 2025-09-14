"use client";

import React from "react";
import { Alert, AlertTitle, AlertDescription } from "@/components/ui/alert";
import { useMessages } from "@/hooks/use-messages";
import { Info, AlertTriangle, XCircle, CheckCircle2, X } from "lucide-react";

function iconFor(variant?: string) {
  switch (variant) {
    case "destructive":
      return <XCircle className="h-5 w-5" />;
    case "success":
      return <CheckCircle2 className="h-5 w-5" />;
    case "warning":
      return <AlertTriangle className="h-5 w-5" />;
    case "info":
      return <Info className="h-5 w-5" />;
    default:
      return <Info className="h-5 w-5" />;
  }
}

export function MessageCenter() {
  const { toasts, dismiss } = useMessages();
  const timersRef = React.useRef<Map<string, number>>(new Map());

  React.useEffect(() => {
    // Schedule auto-dismiss for non-error messages
    toasts.forEach((t: any) => {
      const id = t.id as string;
      if (timersRef.current.has(id)) return;
      // Do not auto-dismiss destructive messages
      if (t?.variant === "destructive") return;
      
      const ms = typeof t?.duration === "number" ? t.duration : 5000;
      const handle = window.setTimeout(() => {
        dismiss(id);
        timersRef.current.delete(id);
      }, ms);
      timersRef.current.set(id, handle);
    });

    // Cleanup timers for removed toasts
    timersRef.current.forEach((handle, id) => {
      if (!toasts.find((t: any) => t.id === id)) {
        window.clearTimeout(handle);
        timersRef.current.delete(id);
      }
    });
  }, [toasts, dismiss]);

  const visible = (toasts || []).filter((t: any) => t.open !== false);
  if (visible.length === 0) return null;

  return (
    <div className="space-y-3" role="region" aria-live="polite" aria-label="Notifications">
      {visible.map((t: any) => (
        <div key={t.id} className="relative">
          <Alert variant={t.variant as any}>
            {iconFor(t.variant)}
            <div>
              {t.title && <AlertTitle className="text-sm font-medium">{t.title}</AlertTitle>}
              {t.description && <AlertDescription className="text-sm">{t.description}</AlertDescription>}
            </div>
            <button
              type="button"
              className="absolute right-2 top-2 rounded-md p-1 text-foreground/60 hover:bg-muted focus:outline-none focus:ring-2"
              aria-label="Dismiss"
              onClick={() => dismiss(t.id)}
            >
              <X className="h-4 w-4" />
            </button>
          </Alert>
        </div>
      ))}
    </div>
  );
}
