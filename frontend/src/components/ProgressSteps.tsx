"use client";

import { CheckCircle2, Circle, Loader2, XCircle } from "lucide-react";
import type { OperationStep, OperationStepStatus } from "@/types";

interface ProgressStepsProps {
  steps: OperationStep[];
}

function StepIcon({ status }: { status: OperationStepStatus }) {
  switch (status) {
    case "in-progress":
      return <Loader2 className="h-4 w-4 animate-spin text-blue-500" />;
    case "done":
      return <CheckCircle2 className="h-4 w-4 text-green-500" />;
    case "error":
      return <XCircle className="h-4 w-4 text-destructive" />;
    case "pending":
    default:
      return <Circle className="h-4 w-4 text-muted-foreground" />;
  }
}

export function ProgressSteps({ steps }: ProgressStepsProps) {
  return (
    <ul className="space-y-2">
      {steps.map((step, idx) => (
        <li key={idx} className="flex items-center gap-2 text-sm">
          <StepIcon status={step.status} />
          <span
            className={
              step.status === "done"
                ? "text-muted-foreground line-through"
                : step.status === "error"
                  ? "text-destructive"
                  : ""
            }
          >
            {step.step}
          </span>
          {step.message && (
            <span className="text-xs text-destructive ml-2">({step.message})</span>
          )}
        </li>
      ))}
    </ul>
  );
}
