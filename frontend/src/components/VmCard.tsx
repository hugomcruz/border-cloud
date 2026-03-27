"use client";

import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { ErrorBanner } from "@/components/ErrorBanner";
import { ProgressSteps } from "@/components/ProgressSteps";
import { WarningBanner } from "@/components/WarningBanner";
import { VmSettingsModal } from "@/components/VmSettingsModal";
import { useOperation } from "@/context/OperationContext";
import { apiFetch } from "@/lib/api";
import {
  Server,
  Wifi,
  Globe,
  Cpu,
  MapPin,
  Play,
  Square,
  Archive,
  RotateCcw,
  Trash2,
  Settings,
  Loader2,
  Lock,
} from "lucide-react";
import { cn } from "@/lib/utils";
import type { VirtualMachine, OperationEvent, OperationStep } from "@/types";

interface VmCardProps {
  vm: VirtualMachine;
  onRefresh: () => void;
}

const statusConfig: Record<string, { dot: string; label: string; text: string }> = {
  running: { dot: "bg-green-500", label: "Running", text: "text-green-700" },
  stopped: { dot: "bg-yellow-400", label: "Stopped", text: "text-yellow-700" },
  archived: { dot: "bg-gray-400", label: "Archived", text: "text-gray-600" },
};

function useSimpleAction(
  vmName: string,
  onRefresh: () => void,
) {
  const { lock, unlock, isLocked: isLockedFn } = useOperation();
  const isLocked = isLockedFn(vmName);
  const [error, setError] = useState<string | null>(null);

  async function run(action: string) {
    if (isLocked) return;
    lock(vmName, action);
    setError(null);
    try {
      await apiFetch(`/api/vms/${encodeURIComponent(vmName)}/${action}`, { method: "POST" });
      onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Operation failed");
    } finally {
      unlock(vmName);
    }
  }

  return { run, error, setError, isLocked };
}

function useSseAction(vmName: string, onRefresh: () => void) {
  const { lock, unlock, isLocked: isLockedFn } = useOperation();
  const isLocked = isLockedFn(vmName);
  const [steps, setSteps] = useState<OperationStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [completedSteps, setCompletedSteps] = useState<string[]>([]);
  const [warning, setWarning] = useState<string | null>(null);

  async function run(action: "archive" | "restore" | "delete") {
    if (isLocked) return;
    lock(vmName, action);
    setSteps([]);
    setError(null);
    setCompletedSteps([]);
    setWarning(null);

    try {
      // Step 1: Start the operation; backend returns { op_id } (202)
      const startRes = await fetch(
        `/api/vms/${encodeURIComponent(vmName)}/${action}`,
        { method: "POST" },
      );
      if (!startRes.ok) {
        setError(`Failed to start ${action} (${startRes.status})`);
        unlock(vmName);
        return;
      }
      const { op_id } = (await startRes.json()) as { op_id: string };

      // Step 2: Connect to the SSE stream for this operation
      const streamRes = await fetch(
        `/api/vms/operations/${encodeURIComponent(op_id)}/stream`,
      );
      if (!streamRes.ok || !streamRes.body) {
        setError(`Failed to connect to operation stream (${streamRes.status})`);
        unlock(vmName);
        return;
      }

      const reader = streamRes.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const pump = (): Promise<void> => reader.read().then(({ done, value }) => {
          if (done) {
            unlock(vmName);
            return;
          }
          buffer += decoder.decode(value, { stream: true });
          const parts = buffer.split("\n\n");
          buffer = parts.pop() ?? "";
          for (const part of parts) {
            const line = part.replace(/^data:\s*/, "").trim();
            if (!line) continue;
            try {
              const event: OperationEvent = JSON.parse(line);
              if (event.kind === "step") {
                const step = event.step;
                if (!step) continue;
                setSteps((prev) => {
                  const idx = prev.findIndex((s) => s.step === step.step);
                  if (idx >= 0) {
                    const next = [...prev];
                    next[idx] = step;
                    return next;
                  }
                  return [...prev, step];
                });
                if (step.status === "done") {
                  setCompletedSteps((prev) => [...prev, step.step]);
                }
              } else if (event.kind === "warning") {
                setWarning(event.message ?? null);
              } else if (event.kind === "complete") {
                unlock(vmName);
                onRefresh();
                return;
              } else if (event.kind === "error") {
                setError(event.message ?? "Unknown error");
                setCompletedSteps(event.completedSteps ?? []);
                unlock(vmName);
                return;
              }
            } catch {
              // ignore malformed SSE lines
            }
          }
          return pump();
        });

      await pump();
    } catch {
      setError("Connection lost");
      unlock(vmName);
    }
  }

  return { run, steps, error, setError, completedSteps, warning, setWarning, isLocked };
}

export function VmCard({ vm, onRefresh }: VmCardProps) {
  const startStop = useSimpleAction(vm.name, onRefresh);
  const sse = useSseAction(vm.name, onRefresh);
  const [showSettings, setShowSettings] = useState(false);
  const [showDeleteDialog, setShowDeleteDialog] = useState(false);

  function handleDeleteConfirm() {
    setShowDeleteDialog(false);
    void sse.run("delete");
  }

  const anyError = startStop.error ?? sse.error;
  const anyCompletedSteps = sse.completedSteps;
  const { getOperation } = useOperation();
  const isThisLocked = sse.isLocked;
  const currentOp = getOperation(vm.name);
  const status = statusConfig[vm.status] ?? { dot: "bg-gray-400", label: vm.status, text: "text-gray-600" };
  const serverType = vm.server_type ?? vm.latest_snapshot?.server_type;
  const location = vm.location ?? vm.latest_snapshot?.location;

  return (
    <Card className="w-full overflow-hidden border border-border shadow-sm hover:shadow-md transition-shadow">
      {showSettings && (
        <VmSettingsModal vmName={vm.name} onClose={() => setShowSettings(false)} />
      )}

      <Dialog open={showDeleteDialog} onOpenChange={setShowDeleteDialog}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Delete {vm.name}?</DialogTitle>
            <DialogDescription>
              This will permanently delete the running instance without creating a snapshot.
              This action cannot be undone.
            </DialogDescription>
          </DialogHeader>
          <div className="flex justify-end gap-2 mt-4">
            <Button variant="outline" onClick={() => setShowDeleteDialog(false)}>
              Cancel
            </Button>
            <Button variant="destructive" onClick={handleDeleteConfirm}>
              Yes, delete
            </Button>
          </div>
        </DialogContent>
      </Dialog>

      {/* Card header */}
      <CardHeader className="pb-3 pt-4 px-4">
        <div className="flex items-start justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className={cn(
              "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
              vm.status === "running" ? "bg-green-100 text-green-700" :
              vm.status === "stopped" ? "bg-yellow-100 text-yellow-700" :
              "bg-gray-100 text-gray-500"
            )}>
              <Server className="h-4 w-4" />
            </div>
            <div className="min-w-0">
              <CardTitle className="text-sm font-semibold leading-tight truncate">{vm.name}</CardTitle>
              <div className="flex items-center gap-1.5 mt-0.5">
                <span className={cn("h-1.5 w-1.5 rounded-full", status.dot)} />
                <span className={cn("text-xs font-medium", status.text)}>{status.label}</span>
              </div>
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {currentOp && (
              <span className="flex items-center gap-1 text-xs font-medium text-blue-600 bg-blue-50 px-2 py-0.5 rounded-full border border-blue-100">
                <Loader2 className="h-3 w-3 animate-spin" />
                {currentOp}…
              </span>
            )}
            {!vm.protected && (
              <button
                onClick={() => setShowSettings(true)}
                aria-label="VM settings"
                className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors"
              >
                <Settings className="h-3.5 w-3.5" />
              </button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent className="px-4 pb-4 space-y-3">
        {/* Meta info */}
        <div className="space-y-1.5">
          {vm.public_ip && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Wifi className="h-3.5 w-3.5 shrink-0" />
              <span className="font-mono">{vm.public_ip}</span>
            </div>
          )}
          {vm.domain && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Globe className="h-3.5 w-3.5 shrink-0" />
              <span>{vm.domain}</span>
            </div>
          )}
          {serverType && (
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <Cpu className="h-3.5 w-3.5 shrink-0" />
              <span className="font-mono">{serverType}</span>
              {location && <><MapPin className="h-3 w-3 ml-1 shrink-0" /><span className="font-mono">{location}</span></>}
            </div>
          )}
        </div>

        {anyError && (
          <ErrorBanner
            message={anyError}
            completedSteps={anyCompletedSteps}
            onDismiss={() => {
              startStop.setError(null);
              sse.setError(null);
            }}
          />
        )}

        {sse.warning && (
          <WarningBanner
            message={sse.warning}
            onDismiss={() => sse.setWarning(null)}
          />
        )}

        {isThisLocked && sse.steps.length > 0 && (
          <ProgressSteps steps={sse.steps} />
        )}

        {/* Actions */}
        <div className="flex gap-1.5 flex-wrap pt-1">
          {vm.protected ? (
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground border border-border rounded-md px-2.5 py-1">
              <Lock className="h-3 w-3" />
              Protected
            </span>
          ) : (
            <>
              {vm.can_start && (
                <Button
                  size="sm"
                  className="h-7 px-2.5 text-xs gap-1.5"
                  onClick={() => void startStop.run("start")}
                  disabled={startStop.isLocked}
                >
                  <Play className="h-3 w-3" />
                  Start
                </Button>
              )}

              {vm.can_stop && (
                <Button
                  size="sm"
                  variant="outline"
                  className="h-7 px-2.5 text-xs gap-1.5"
                  onClick={() => void startStop.run("stop")}
                  disabled={startStop.isLocked}
                >
                  <Square className="h-3 w-3" />
                  Stop
                </Button>
              )}

              {vm.can_archive && (
                <Button
                  size="sm"
                  variant="secondary"
                  className="h-7 px-2.5 text-xs gap-1.5"
                  onClick={() => void sse.run("archive")}
                  disabled={sse.isLocked}
                >
                  <Archive className="h-3 w-3" />
                  Archive
                </Button>
              )}

              {vm.can_restore && (
                <Button
                  size="sm"
                  className="h-7 px-2.5 text-xs gap-1.5"
                  onClick={() => void sse.run("restore")}
                  disabled={sse.isLocked}
                >
                  <RotateCcw className="h-3 w-3" />
                  Restore
                </Button>
              )}

              {vm.can_archive && (
                <Button
                  size="sm"
                  variant="destructive"
                  className="h-7 px-2.5 text-xs gap-1.5"
                  onClick={() => setShowDeleteDialog(true)}
                  disabled={sse.isLocked || startStop.isLocked}
                >
                  <Trash2 className="h-3 w-3" />
                  Delete
                </Button>
              )}
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

