"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import type { VmConfig } from "@/types";
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
