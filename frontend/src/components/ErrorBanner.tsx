"use client";

import { X } from "lucide-react";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";

interface ErrorBannerProps {
  message: string;
  completedSteps?: string[];
  onDismiss?: () => void;
}

export function ErrorBanner({ message, completedSteps, onDismiss }: ErrorBannerProps) {
  return (
    <Alert variant="destructive" className="relative">
      <AlertTitle>Something went wrong</AlertTitle>
      <AlertDescription>
        <p>{message}</p>
        {completedSteps && completedSteps.length > 0 && (
          <div className="mt-2">
            <p className="text-xs font-semibold">Completed before failure:</p>
            <ul className="list-disc list-inside text-xs mt-1">
              {completedSteps.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          </div>
        )}
      </AlertDescription>
      {onDismiss && (
        <Button
          variant="ghost"
          size="icon"
          className="absolute right-2 top-2 h-6 w-6"
          onClick={onDismiss}
          aria-label="Dismiss error"
        >
          <X className="h-3 w-3" />
        </Button>
      )}
    </Alert>
  );
}
