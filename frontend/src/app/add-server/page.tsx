"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { Sidebar } from "@/components/Sidebar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ErrorBanner } from "@/components/ErrorBanner";
import { ProgressSteps } from "@/components/ProgressSteps";
import { WarningBanner } from "@/components/WarningBanner";
import { apiFetch } from "@/lib/api";
import { useProject } from "@/context/ProjectContext";
import type { OperationEvent, OperationStep } from "@/types";
import { Server, Cpu, HardDrive, Globe, Container, ArrowLeft, CheckCircle2, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

const SERVER_TYPES = [
  { value: "cpx22", label: "CPX22", specs: "2 vCPUs · 4 GB RAM · 80 GB Disk", price: "€8.49/mo" },
  { value: "cpx32", label: "CPX32", specs: "4 vCPUs · 8 GB RAM · 160 GB Disk", price: "€14.49/mo" },
  { value: "cpx42", label: "CPX42", specs: "8 vCPUs · 16 GB RAM · 320 GB Disk", price: "€25.99/mo" },
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

export default function AddServerPage() {
  const router = useRouter();
  const { selectedProject } = useProject();

  // Form fields
  const [name, setName] = useState("");
  const [fqdn, setFqdn] = useState("");
  const [serverType, setServerType] = useState("cpx22");
  const [osImage, setOsImage] = useState("debian-13");
  const [installK3s, setInstallK3s] = useState(false);

  // Project resources
  const [resources, setResources] = useState<ProjectResources | null>(null);
  const [resourcesLoading, setResourcesLoading] = useState(true);

  // Operation state
  const [submitting, setSubmitting] = useState(false);
  const [steps, setSteps] = useState<OperationStep[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [warning, setWarning] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  // doneRef lets the pump() closure check completion without stale state
  const doneRef = useRef(false);

  // Load project resources
  useEffect(() => {
    if (!selectedProject) return;
    setResourcesLoading(true);
    apiFetch<ProjectResources>(`/api/vms/resources?project_id=${selectedProject.id}`)
      .then((r) => setResources(r))
      .catch(() => setResources({ ssh_keys: [], networks: [], firewalls: [] }))
      .finally(() => setResourcesLoading(false));
  }, [selectedProject]);

  // k3s requires Debian 13
  useEffect(() => {
    if (osImage !== "debian-13") setInstallK3s(false);
  }, [osImage]);

  // Navigate home 1.5s after success — runs as a proper effect so no stale closure
  useEffect(() => {
    if (!done) return;
    const t = setTimeout(() => { window.location.href = "/"; }, 1500);
    return () => clearTimeout(t);
  }, [done]);

  function markDone() {
    if (doneRef.current) return; // prevent double-call
    doneRef.current = true;
    setSubmitting(false);
    setDone(true);
  }

  function handleLogout() {
    void fetch("/api/auth/logout", { method: "POST" }).finally(() => {
      window.location.href = "/login";
    });
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!name.trim() || !selectedProject) return;

    doneRef.current = false;
    setSubmitting(true);
    setSteps([]);
    setError(null);
    setWarning(null);
    setDone(false);

    try {
      const startRes = await fetch(
        `/api/vms/provision?project_id=${selectedProject.id}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: name.trim(),
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
            // Stream closed — use doneRef (not stale state) to check if complete fired
            if (!doneRef.current) {
              setSubmitting(false);
            }
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
                markDone();
                return;
              } else if (event.kind === "error") {
                setError(event.message ?? "Unknown error");
                setSubmitting(false);
                return;
              }
            } catch {
              /* ignore malformed SSE lines */
            }
          }
          return pump();
        });

      await pump();
    } catch {
      setError("Connection lost");
      setSubmitting(false);
    }
  }

  return (
    <div className="flex h-screen bg-background text-foreground">
      <Sidebar onLogout={handleLogout} />

      <main className="flex-1 overflow-y-auto">
        {/* Page header */}
        <header className="flex items-center gap-4 border-b border-border bg-card px-6 py-4">
          <button
            onClick={() => router.push("/")}
            className="flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground transition-colors"
            disabled={submitting}
          >
            <ArrowLeft className="h-4 w-4" />
            Back
          </button>
          <div className="h-4 w-px bg-border" />
          <div className="flex items-center gap-2">
            <Server className="h-5 w-5 text-muted-foreground" />
            <h1 className="text-base font-semibold">Add New Server</h1>
          </div>
          <p className="text-sm text-muted-foreground hidden sm:block">
            Datacenter is selected automatically: Falkenstein → Nuremberg → Helsinki
          </p>
        </header>

        <div className="p-6 max-w-4xl">
          {done ? (
            /* ── Success state ── */
            <div className="space-y-6">
              <div className="flex items-center gap-3 rounded-lg border border-green-200 bg-green-50 dark:border-green-800 dark:bg-green-950/30 px-5 py-4">
                <CheckCircle2 className="h-5 w-5 text-green-600 shrink-0" />
                <div>
                  <p className="font-medium text-green-800 dark:text-green-300">
                    Server provisioned successfully
                  </p>
                  <p className="text-sm text-green-700 dark:text-green-400 mt-0.5">
                    <span className="font-mono font-semibold">{name}</span> is ready.
                    Taking you to the dashboard…
                  </p>
                </div>
              </div>
              {steps.length > 0 && <ProgressSteps steps={steps} />}
              {warning && <WarningBanner message={warning} onDismiss={() => setWarning(null)} />}
              <Button onClick={() => { window.location.href = "/"; }}>
                Go to Dashboard now
              </Button>
            </div>
          ) : submitting ? (
            /* ── Provisioning in progress ── */
            <div className="space-y-6">
              <div className="flex items-center gap-3 rounded-lg border border-border bg-card px-5 py-4">
                <Loader2 className="h-5 w-5 text-muted-foreground animate-spin shrink-0" />
                <div>
                  <p className="font-medium">
                    Provisioning <span className="font-mono">{name}</span>…
                  </p>
                  <p className="text-sm text-muted-foreground mt-0.5">
                    This takes about 30–60 seconds. Please wait.
                  </p>
                </div>
              </div>
              {steps.length > 0 && <ProgressSteps steps={steps} />}
              {error && <ErrorBanner message={error} onDismiss={() => setError(null)} />}
              {warning && <WarningBanner message={warning} onDismiss={() => setWarning(null)} />}
            </div>
          ) : (
            /* ── Form ── */
            <form onSubmit={(e) => void handleSubmit(e)}>
              {error && (
                <div className="mb-6">
                  <ErrorBanner message={error} onDismiss={() => setError(null)} />
                </div>
              )}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

                {/* ── Left column: identity + instance type ── */}
                <div className="space-y-6">
                  <section className="rounded-lg border border-border bg-card p-5 space-y-4">
                    <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
                      Identity
                    </h2>

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

                    <div className="space-y-1.5">
                      <label
                        className="text-sm font-medium flex items-center gap-1.5"
                        htmlFor="fqdn"
                      >
                        <Globe className="h-3.5 w-3.5" />
                        FQDN (Cloudflare DNS)
                      </label>
                      <Input
                        id="fqdn"
                        placeholder="e.g. web-01.example.com"
                        value={fqdn}
                        onChange={(e) => setFqdn(e.target.value)}
                      />
                      <p className="text-xs text-muted-foreground">
                        Leave blank to skip DNS record creation.
                      </p>
                    </div>
                  </section>

                  {/* Instance type */}
                  <section className="rounded-lg border border-border bg-card p-5 space-y-3">
                    <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                      <Cpu className="h-3.5 w-3.5" />
                      Instance Type
                    </h2>
                    <div className="space-y-2">
                      {SERVER_TYPES.map((t) => (
                        <button
                          key={t.value}
                          type="button"
                          onClick={() => setServerType(t.value)}
                          className={cn(
                            "w-full flex items-center justify-between rounded-md border px-4 py-3 text-left text-sm transition-colors",
                            serverType === t.value
                              ? "border-primary bg-primary/5 text-foreground"
                              : "border-border bg-background text-muted-foreground hover:border-muted-foreground/50 hover:text-foreground",
                          )}
                        >
                          <div>
                            <span className="font-semibold">{t.label}</span>
                            <p className="text-xs mt-0.5 text-muted-foreground">{t.specs}</p>
                          </div>
                          <span className="text-xs font-semibold shrink-0 ml-4 text-foreground">{t.price}</span>
                        </button>
                      ))}
                    </div>
                  </section>
                </div>

                {/* ── Right column: OS + k3s + resources ── */}
                <div className="space-y-6">
                  {/* OS Image */}
                  <section className="rounded-lg border border-border bg-card p-5 space-y-3">
                    <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground flex items-center gap-1.5">
                      <HardDrive className="h-3.5 w-3.5" />
                      Image
                    </h2>
                    <div className="space-y-2">
                      {OS_IMAGES.map((img) => (
                        <button
                          key={img.value}
                          type="button"
                          onClick={() => setOsImage(img.value)}
                          className={cn(
                            "w-full flex items-center rounded-md border px-4 py-3 text-left text-sm transition-colors",
                            osImage === img.value
                              ? "border-primary bg-primary/5 text-foreground font-semibold"
                              : "border-border text-muted-foreground hover:border-muted-foreground/50 hover:text-foreground",
                          )}
                        >
                          {img.label}
                        </button>
                      ))}
                    </div>
                  </section>

                  {/* Kubernetes */}
                  <section
                    className={cn(
                      "rounded-lg border bg-card p-5 transition-opacity",
                      osImage !== "debian-13"
                        ? "opacity-40 pointer-events-none border-border"
                        : "border-border",
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
                        <div className="flex items-center gap-1.5 text-sm font-semibold">
                          <Container className="h-3.5 w-3.5" />
                          Install Kubernetes (k3s)
                        </div>
                        <p className="text-xs text-muted-foreground mt-1">
                          Installs k3s with Traefik disabled. Only available with Debian 13.
                        </p>
                      </div>
                    </label>
                  </section>

                  {/* Auto-configured resources */}
                  <section className="rounded-lg border border-border bg-card p-5 space-y-2">
                    <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground">
                      Auto-configured from Project
                    </h2>
                    {resourcesLoading ? (
                      <p className="text-xs text-muted-foreground">Loading…</p>
                    ) : resources ? (
                      <div className="text-xs text-muted-foreground space-y-1.5">
                        <div className="flex gap-2">
                          <span className="w-32 shrink-0 font-medium text-foreground">SSH keys</span>
                          <span>
                            {resources.ssh_keys.length > 0
                              ? resources.ssh_keys.map((k) => k.name).join(", ")
                              : "none"}
                          </span>
                        </div>
                        <div className="flex gap-2">
                          <span className="w-32 shrink-0 font-medium text-foreground">
                            Private networks
                          </span>
                          <span>
                            {resources.networks.length > 0
                              ? resources.networks.map((n) => n.name).join(", ")
                              : "none"}
                          </span>
                        </div>
                        <div className="flex gap-2">
                          <span className="w-32 shrink-0 font-medium text-foreground">Firewalls</span>
                          <span>
                            {resources.firewalls.length > 0
                              ? resources.firewalls.map((f) => f.name).join(", ")
                              : "none"}
                          </span>
                        </div>
                        <div className="flex gap-2">
                          <span className="w-32 shrink-0 font-medium text-foreground">Networking</span>
                          <span>IPv4 enabled · IPv6 disabled</span>
                        </div>
                      </div>
                    ) : null}
                  </section>
                </div>
              </div>

              {/* Actions */}
              <div className="mt-6 flex items-center gap-3">
                <Button type="submit" disabled={!name.trim()}>
                  Create Server
                </Button>
                <Button type="button" variant="outline" onClick={() => router.push("/")}>
                  Cancel
                </Button>
              </div>
            </form>
          )}
        </div>
      </main>
    </div>
  );
}
