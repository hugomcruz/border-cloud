"use client";

import { useEffect } from "react";

interface WarningBannerProps {
  message: string;
  onDismiss: () => void;
  autoDismissMs?: number;
}

export function WarningBanner({ message, onDismiss, autoDismissMs = 10000 }: WarningBannerProps) {
  useEffect(() => {
    const timer = setTimeout(onDismiss, autoDismissMs);
    return () => clearTimeout(timer);
  }, [onDismiss, autoDismissMs]);

  return (
    <div
      role="alert"
      className="flex items-start justify-between gap-4 rounded-md border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm text-yellow-800"
    >
      <span>{message}</span>
      <button
        onClick={onDismiss}
        aria-label="Dismiss warning"
        className="shrink-0 font-semibold hover:opacity-70"
      >
        ×
      </button>
    </div>
  );
}
