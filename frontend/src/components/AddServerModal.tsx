"use client";

import { useEffect, useRef, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/ErrorBanner";
import { ProgressSteps } from "@/components/ProgressSteps";
import { WarningBanner } from "@/components/WarningBanner";
import { apiFetch } from "@/lib/api";
import type { OperationEvent, OperationStep } from "@/types";
import { Server, Cpu, HardDrive, Globe, Container, CheckCircle2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const SERVER_TYPES = [
  { value: "cpx22", label: "CPX22", specs: "2 vCPUs · 4 GB RAM · 80 GB Disk", price: "EUR 8.49/mo" },
  { value: "cpx32", label: "CPX32", specs: "4 vCPUs · 8 GB RAM · 160 GB Disk", price: "EUR 14.49/mo" },
  { value: "cpx42", label: "CPX42", specs: "8 vCPUs · 16 GB RAM · 320 GB Disk", price: "EUR 25.99/mo" },
] as const;

const OS_IMAGES = [
  { value: "debian-13", label: "Debian 13" },
  { value: "centos-stream-10", label: "CentOS Stream 10" },
  { value: "rocky-linux-10", label: "Rocky Linux 10" },
] as const;

interface ProjectResources {
  ssh_keys: { id: number; name: string }[];
  networks: { id: number; name: string }[];
  firewalls: { id: number; name: string }[];
}

interface AddServerModalProps {
  projectId: number;
  onClose: () => void;
  onDone: (serverName: string) => void;
}

export function AddServerModal({ projectId, onClose, onDone }: AddServerModalProps) {
  // Form fields
  const [name, setName] = useState("");
  const [fqdn, setFqdn] = useState("");
  const [serverType, setServerType] = useState<string>("cpx22");
  const [osImage, setOsImage] = useState<string>("debian-13");
  const [installK3s, setInstallK3s] = useState(false);

  // Project resources (auto-selected)
  const [resources, setResources] = useState<ProjectResources | null>(null);
  const [resourcesLoading, setResourcesLoading] = useState(true);

  // Operation state
  const [submitting, setSubmitting] = useState(false);
  const [done, setDone] = useState(false);
  const [lastCreated, setLastCreated] = useState("");
  const [steps, setSteps] = useState<OperationStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  // doneRef avoids stale closure in pump()
  const doneRef = useRef(false);
  const hadErrorRef = useRef(false);

  // Load project resources on mount
  useEffect(() => {
    setResourcesLoading(true);
    apiFetch<ProjectResources>(`/api/vms/resources?project_id=${projectId}`)
      .then((r) => setResources(r))
      .catch(() => setResources({ ssh_keys: [], networks: [], firewalls: [] }))
      .finally(() => setResourcesLoading(false));
  }, [projectId]);

  // k3s requires Debian 13
  useEffect(() => {
    if (osImage !== "debian-13") setInstallK3s(false);
  }, [osImage]);

  function markDone(serverName: string) {
    if (doneRef.current) return;
    doneRef.current = true;
    setSubmitting(false);
    setDone(true);
    setLastCreated(serverName);
    onDone(serverName);
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim()) return;

    const serverName = name.trim();
    doneRef.current = false;
    hadErrorRef.current = false;
    setSubmitting(true);
    setSteps([]);
    setError(null);
    setWarning(null);
    setDone(false);
    setLastCreated("");

    try {
      const startRes = await fetch(
        `/api/vms/provision?project_id=${projectId}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: serverName,
            server_type: serverType,
            os_image: osImage,
            fqdn: fqdn.trim() || null,
            install_k3s: installK3s,
            firewall_ids: resources?.firewalls.map((f) => f.id) ?? [],
            network_ids: resources?.networks.map((n) => n.id) ?? [],
            ssh_key_names: resources?.ssh_keys.map((k) => k.name) ?? [],
          }),
        },
      );

      if (!startRes.ok) {
        const body = (await startRes.json().catch(() => ({}))) as { detail?: string };
        setError(body.detail ?? `Failed to start provisioning (${startRes.status})`);
        setSubmitting(false);
        return;
      }

      const { op_id } = (await startRes.json()) as { op_id: string };

      const streamRes = await fetch(`/api/vms/operations/${encodeURIComponent(op_id)}/stream`);
      if (!streamRes.ok || !streamRes.body) {
        setError(`Failed to connect to operation stream (${streamRes.status})`);
        setSubmitting(false);
        return;
      }

      const reader = streamRes.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      const pump = (): Promise<void> =>
        reader.read().then(({ done: streamDone, value }) => {
          if (streamDone) {
            if (!doneRef.current && !hadErrorRef.current) {
              markDone(serverName);
              return;
            }
            if (!doneRef.current) setSubmitting(false);
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
              } else if (event.kind === "warning") {
                setWarning(event.message ?? null);
              } else if (event.kind === "complete") {
                markDone(serverName);
                return;
              } else if (event.kind === "error") {
                hadErrorRef.current = true;
                setError(event.message ?? "Unknown error");
                setSubmitting(false);
                return;
              }
            } catch {
              // ignore malformed SSE
            }
          }
          return pump();
        });

      await pump();
    } catch {
      hadErrorRef.current = true;
      setError("Connection lost");
      setSubmitting(false);
    }
  }

  return (
    <Dialog open={true} onOpenChange={(o) => { if (!o && !submitting) onClose(); }}>
      {/* max-h + overflow makes the dialog scroll on small screens */}
      <DialogContent className="max-w-lg max-h-[90vh] flex flex-col p-0 gap-0">
        <div className="px-6 pt-6 pb-4 border-b border-border shrink-0">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <Server className="h-5 w-5" />
              Add New Server
            </DialogTitle>
            <DialogDescription>
              Provision a new VM. Datacenter is selected automatically (Falkenstein → Nuremberg → Helsinki).
            </DialogDescription>
          </DialogHeader>
        </div>

        <div className="flex-1 overflow-y-auto px-6 py-5">
          {done ? (
            /* ── Success ── */
            <div className="space-y-4">
              <div className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950/30 px-4 py-3">
                <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0" />
                <div>
                  <p className="text-sm font-medium text-green-800 dark:text-green-300">
                    <span className="font-mono font-semibold">{lastCreated}</span> provisioned successfully.
                  </p>
                </div>
              </div>
              {steps.length > 0 && <ProgressSteps steps={steps} />}
              {warning && <WarningBanner message={warning} onDismiss={() => setWarning(null)} />}
            </div>
          ) : submitting ? (
            /* ── In progress ── */
            <div className="space-y-4">
              <div className="flex items-center gap-3 rounded-lg border border-border bg-muted/40 px-4 py-3">
                <Loader2 className="h-5 w-5 text-muted-foreground animate-spin shrink-0" />
                <div>
                  <p className="text-sm font-medium">Provisioning <span className="font-mono">{name}</span>…</p>
                  <p className="text-xs text-muted-foreground mt-0.5">This takes about 30–60 seconds.</p>
                </div>
              </div>
              {steps.length > 0 && <ProgressSteps steps={steps} />}
              {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
              {warning && <WarningBanner message={warning} onDismiss={() => setWarning(null)} />}
            </div>
          ) : (
            /* ── Form ── */
            <form id="add-server-form" onSubmit={(e) => void handleSubmit(e)} className="space-y-5">
              {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}

              {/* Server name */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium" htmlFor="server-name">
                  Server Name <span className="text-destructive">*</span>
                </label>
                <Input
                  id="server-name"
                  placeholder="e.g. web-01"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  required
                />
              </div>

              {/* FQDN */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium flex items-center gap-1.5" htmlFor="fqdn">
                  <Globe className="h-3.5 w-3.5" />
                  FQDN (Cloudflare DNS)
                </label>
                <Input
                  id="fqdn"
                  placeholder="e.g. web-01.example.com"
                  value={fqdn}
                  onChange={(e) => setFqdn(e.target.value)}
                />
                <p className="text-xs text-muted-foreground">Leave blank to skip DNS record creation.</p>
              </div>

              {/* Instance type */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium flex items-center gap-1.5">
                  <Cpu className="h-3.5 w-3.5" />
                  Instance Type
                </label>
                <div className="space-y-2">
                  {SERVER_TYPES.map((t) => (
                    <button
                      key={t.value}
                      type="button"
                      onClick={() => setServerType(t.value)}
                      className={cn(
                        "w-full flex items-center justify-between rounded-md border px-3 py-2.5 text-left text-sm transition-colors",
                        serverType === t.value
                          ? "border-primary bg-primary/5 text-foreground"
                          : "border-border bg-background text-muted-foreground hover:border-muted-foreground/50 hover:text-foreground",
                      )}
                    >
                      <div className="min-w-0">
                        <span className="font-medium">{t.label}</span>
                        <p className="text-xs text-muted-foreground mt-0.5 truncate">{t.specs}</p>
                      </div>
                      <span className="text-xs font-semibold shrink-0 ml-3 text-foreground">{t.price}</span>
                    </button>
                  ))}
                </div>
              </div>

              {/* OS Image */}
              <div className="space-y-1.5">
                <label className="text-sm font-medium flex items-center gap-1.5">
                  <HardDrive className="h-3.5 w-3.5" />
                  Image
                </label>
                <div className="flex gap-2 flex-wrap">
                  {OS_IMAGES.map((img) => (
                    <button
                      key={img.value}
                      type="button"
                      onClick={() => setOsImage(img.value)}
                      className={cn(
                        "rounded-md border px-3 py-1.5 text-sm transition-colors",
                        osImage === img.value
                          ? "border-primary bg-primary/5 text-foreground font-medium"
                          : "border-border text-muted-foreground hover:border-muted-foreground/50 hover:text-foreground",
                      )}
                    >
                      {img.label}
                    </button>
                  ))}
                </div>
              </div>

              {/* Kubernetes toggle */}
              <div
                className={cn(
                  "rounded-md border p-3 transition-opacity",
                  osImage !== "debian-13" ? "opacity-40 pointer-events-none border-border" : "border-border",
                )}
              >
                <label className="flex items-start gap-3 cursor-pointer">
                  <input
                    type="checkbox"
                    className="mt-0.5 h-4 w-4 rounded accent-primary"
                    checked={installK3s}
                    onChange={(e) => setInstallK3s(e.target.checked)}
                    disabled={osImage !== "debian-13"}
                  />
                  <div>
                    <div className="flex items-center gap-1.5 text-sm font-medium">
                      <Container className="h-3.5 w-3.5" />
                      Install Kubernetes (k3s)
                    </div>
                    <p className="text-xs text-muted-foreground mt-0.5">
                      Installs k3s with Traefik disabled. Only available with Debian 13.
                    </p>
                  </div>
                </label>
              </div>

              {/* Auto-configured resources */}
              {!resourcesLoading && resources && (
                <div className="rounded-md bg-muted/40 border border-border px-3 py-2.5 text-xs text-muted-foreground space-y-0.5">
                  <p className="font-medium text-foreground mb-1">Auto-configured from project</p>
                  <p>SSH keys: {resources.ssh_keys.length > 0 ? resources.ssh_keys.map((k) => k.name).join(", ") : "none"}</p>
                  <p>Networks: {resources.networks.length > 0 ? resources.networks.map((n) => n.name).join(", ") : "none"}</p>
                  <p>Firewalls: {resources.firewalls.length > 0 ? resources.firewalls.map((f) => f.name).join(", ") : "none"}</p>
                  <p>IPv4: enabled · IPv6: disabled</p>
                </div>
              )}
            </form>
          )}
        </div>

        {/* Sticky footer */}
        <div className="px-6 py-4 border-t border-border shrink-0 flex justify-end gap-2">
          {done ? (
            <Button type="button" onClick={onClose}>
              Close
            </Button>
          ) : (
            <>
              <Button type="button" variant="outline" onClick={onClose} disabled={submitting}>
                Cancel
              </Button>
              <Button
                type="submit"
                form="add-server-form"
                disabled={submitting || !name.trim()}
              >
                {submitting ? "Provisioning…" : "Create Server"}
              </Button>
            </>
          )}
        </div>
      </DialogContent>
    </Dialog>
  );
}
