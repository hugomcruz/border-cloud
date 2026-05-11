"use client";

import { useEffect, useState } from "react";
import { Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { HetznerProject, VmConfig, VmFirewallTarget } from "@/types";
import { HETZNER_SERVER_TYPES } from "@/types";

interface VmSettingsModalProps {
  vmName: string;
  onClose: () => void;
}

export function VmSettingsModal({ vmName, onClose }: VmSettingsModalProps) {
  const [domain, setDomain] = useState("");
  const [serverType, setServerType] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Firewall targets
  const [targets, setTargets] = useState<VmFirewallTarget[]>([]);
  const [projects, setProjects] = useState<HetznerProject[]>([]);
  const [newProjectId, setNewProjectId] = useState("");
  const [newFirewallName, setNewFirewallName] = useState("");
  const [addingTarget, setAddingTarget] = useState(false);
  const [targetError, setTargetError] = useState<string | null>(null);

  useEffect(() => {
    const loadAll = async () => {
      try {
        const [configData, targetData, projectData] = await Promise.all([
          apiFetch<{ vm_configs: VmConfig[] }>("/api/config/vm-configs"),
          apiFetch<{ targets: VmFirewallTarget[] }>(`/api/config/vm-configs/by-name/${encodeURIComponent(vmName)}/firewall-targets`),
          apiFetch<HetznerProject[]>("/api/admin/projects"),
        ]);
        const cfg = configData.vm_configs.find((c) => c.vm_name === vmName);
        if (cfg) {
          setDomain(cfg.domain ?? "");
          setServerType(cfg.preferred_server_type ?? "");
        }
        setTargets(targetData.targets);
        setProjects(projectData);
        if (projectData.length > 0) setNewProjectId(String(projectData[0].id));
      } catch { /* start with empty fields */ }
      finally { setLoading(false); }
    };
    void loadAll();
  }, [vmName]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await apiFetch(`/api/config/vm-configs/by-name/${encodeURIComponent(vmName)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain: domain.trim() || null,
          preferred_server_type: serverType.trim() || null,
        }),
      });
      setSaved(true);
      setTimeout(onClose, 800);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  async function handleAddTarget() {
    if (!newProjectId || !newFirewallName.trim()) return;
    setAddingTarget(true);
    setTargetError(null);
    try {
      const created = await apiFetch<VmFirewallTarget>(
        `/api/config/vm-configs/by-name/${encodeURIComponent(vmName)}/firewall-targets`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ project_id: Number(newProjectId), firewall_name: newFirewallName.trim() }),
        }
      );
      setTargets((prev) => [...prev, created]);
      setNewFirewallName("");
    } catch (err) {
      setTargetError(err instanceof Error ? err.message : "Failed to add target");
    } finally {
      setAddingTarget(false);
    }
  }

  async function handleDeleteTarget(targetId: number) {
    try {
      await apiFetch(
        `/api/config/vm-configs/by-name/${encodeURIComponent(vmName)}/firewall-targets/${targetId}`,
        { method: "DELETE" }
      );
      setTargets((prev) => prev.filter((t) => t.id !== targetId));
    } catch (err) {
      setTargetError(err instanceof Error ? err.message : "Failed to delete target");
    }
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg bg-card text-card-foreground p-6 shadow-xl space-y-5 border border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">VM Settings — {vmName}</h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground text-xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <div className="space-y-5">
            {/* ── Domain ── */}
            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="domain">
                Domain (for DNS update on restore)
              </label>
              <Input
                id="domain"
                placeholder="e.g. myvm.example.com"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Must match an existing Cloudflare A record. Leave blank to skip DNS update.
              </p>
            </div>

            {/* ── Server type ── */}
            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="server-type">
                Preferred server type (for restore)
              </label>
              <select
                id="server-type"
                value={serverType}
                onChange={(e) => setServerType(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">— use snapshot default —</option>
                {HETZNER_SERVER_TYPES.map((t) => (
                  <option key={t} value={t}>{t}</option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                Overrides the type stored in the snapshot label. The restore will
                upgrade automatically if this type is unavailable.
              </p>
            </div>

            {/* ── Cross-project firewall targets ── */}
            <div className="space-y-2">
              <p className="text-sm font-medium">Firewall targets on restore</p>
              <p className="text-xs text-muted-foreground">
                When this VM is restored, its new IP will also be pushed to these firewalls on other projects.
              </p>

              {targets.length > 0 && (
                <ul className="divide-y divide-border rounded-md border border-border text-sm">
                  {targets.map((t) => (
                    <li key={t.id} className="flex items-center justify-between px-3 py-2">
                      <span>
                        <span className="font-medium">{t.project_name}</span>
                        <span className="text-muted-foreground mx-1">/</span>
                        <span className="font-mono">{t.firewall_name}</span>
                      </span>
                      <button
                        onClick={() => void handleDeleteTarget(t.id)}
                        className="text-muted-foreground hover:text-destructive transition-colors p-1 rounded"
                        title="Remove target"
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </li>
                  ))}
                </ul>
              )}

              <div className="flex gap-2 items-end">
                <div className="flex-1 space-y-1">
                  <label className="text-xs text-muted-foreground">Project</label>
                  <select
                    value={newProjectId}
                    onChange={(e) => setNewProjectId(e.target.value)}
                    className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
                  >
                    {projects.map((p) => (
                      <option key={p.id} value={String(p.id)}>{p.name}</option>
                    ))}
                  </select>
                </div>
                <div className="flex-1 space-y-1">
                  <label className="text-xs text-muted-foreground">Firewall name</label>
                  <Input
                    placeholder="fw-internal"
                    value={newFirewallName}
                    onChange={(e) => setNewFirewallName(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") void handleAddTarget(); }}
                  />
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  disabled={addingTarget || !newFirewallName.trim()}
                  onClick={() => void handleAddTarget()}
                >
                  {addingTarget ? "Adding…" : "Add"}
                </Button>
              </div>
              {targetError && <p className="text-xs text-destructive">{targetError}</p>}
            </div>

            {error && <p className="text-sm text-destructive">{error}</p>}
            {saved && <p className="text-sm text-green-400">Saved!</p>}

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={onClose} disabled={saving}>
                Cancel
              </Button>
              <Button onClick={() => void handleSave()} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


interface VmSettingsModalProps {
  vmName: string;
  onClose: () => void;
}

export function VmSettingsModal({ vmName, onClose }: VmSettingsModalProps) {
  const [domain, setDomain] = useState("");
  const [serverType, setServerType] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  // Load existing config on mount
  useEffect(() => {
    apiFetch<{ vm_configs: VmConfig[] }>("/api/config/vm-configs")
      .then((data) => {
        const cfg = data.vm_configs.find((c) => c.vm_name === vmName);
        if (cfg) {
          setDomain(cfg.domain ?? "");
          setServerType(cfg.preferred_server_type ?? "");
        }
      })
      .catch(() => {/* start with empty fields */})
      .finally(() => setLoading(false));
  }, [vmName]);

  async function handleSave() {
    setSaving(true);
    setError(null);
    setSaved(false);
    try {
      await apiFetch(`/api/config/vm-configs/by-name/${encodeURIComponent(vmName)}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          domain: domain.trim() || null,
          preferred_server_type: serverType.trim() || null,
        }),
      });
      setSaved(true);
      setTimeout(onClose, 800);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    /* Backdrop */
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40"
      onClick={onClose}
    >
      {/* Panel */}
      <div
        className="w-full max-w-md rounded-lg bg-card text-card-foreground p-6 shadow-xl space-y-5 border border-border"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">VM Settings — {vmName}</h2>
          <button
            onClick={onClose}
            className="text-muted-foreground hover:text-foreground text-xl leading-none"
            aria-label="Close"
          >
            ×
          </button>
        </div>

        {loading ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : (
          <div className="space-y-4">
            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="domain">
                Domain (for DNS update on restore)
              </label>
              <Input
                id="domain"
                placeholder="e.g. myvm.example.com"
                value={domain}
                onChange={(e) => setDomain(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                Must match an existing Cloudflare A record. Leave blank to skip DNS update.
              </p>
            </div>

            <div className="space-y-1">
              <label className="text-sm font-medium" htmlFor="server-type">
                Preferred server type (for restore)
              </label>
              <select
                id="server-type"
                value={serverType}
                onChange={(e) => setServerType(e.target.value)}
                className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm shadow-sm focus:outline-none focus:ring-2 focus:ring-ring"
              >
                <option value="">— use snapshot default —</option>
                {HETZNER_SERVER_TYPES.map((t) => (
                  <option key={t} value={t}>
                    {t}
                  </option>
                ))}
              </select>
              <p className="text-xs text-muted-foreground">
                Overrides the type stored in the snapshot label. The restore will
                upgrade automatically if this type is unavailable.
              </p>
            </div>

            {error && (
              <p className="text-sm text-destructive">{error}</p>
            )}
            {saved && (
              <p className="text-sm text-green-400">Saved!</p>
            )}

            <div className="flex justify-end gap-2 pt-1">
              <Button variant="outline" onClick={onClose} disabled={saving}>
                Cancel
              </Button>
              <Button onClick={handleSave} disabled={saving}>
                {saving ? "Saving…" : "Save"}
              </Button>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
