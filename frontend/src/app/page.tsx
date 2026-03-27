"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { apiFetch } from "@/lib/api";
import { VmCard } from "@/components/VmCard";
import { Sidebar } from "@/components/Sidebar";
import { ErrorBanner } from "@/components/ErrorBanner";
import { WarningBanner } from "@/components/WarningBanner";
import { Skeleton } from "@/components/ui/skeleton";
import { useOperation } from "@/context/OperationContext";
import { RefreshCw, Server } from "lucide-react";
import type { VirtualMachine } from "@/types";

export default function Home() {
  const [vms, setVms] = useState<VirtualMachine[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [fetchError, setFetchError] = useState<string | null>(null);
  const [firewallWarning, setFirewallWarning] = useState<string | null>(null);

  const refreshVms = useCallback(async (manual = false) => {
    if (manual) setRefreshing(true);
    try {
      const data = await apiFetch<{ vms: VirtualMachine[] }>("/api/vms");
      setVms(data.vms);
      setFetchError(null);
    } catch (err) {
      setFetchError(err instanceof Error ? err.message : "Failed to load VMs");
    } finally {
      setLoading(false);
      if (manual) setRefreshing(false);
    }
  }, []);

  const syncFirewall = useCallback(async () => {
    try {
      const { ip } = await apiFetch<{ ip: string }>("/api/ip");
      await apiFetch("/api/firewall/sync", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ip }),
      });
    } catch {
      setFirewallWarning(
        "Could not sync your IP with the firewall. Some VM operations may be blocked."
      );
    }
  }, []);

  const { anyRunning } = useOperation();
  const autoRefreshRef = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    if (anyRunning) {
      autoRefreshRef.current = setInterval(() => { void refreshVms(); }, 15_000);
    } else {
      if (autoRefreshRef.current !== null) {
        clearInterval(autoRefreshRef.current);
        autoRefreshRef.current = null;
      }
    }
    return () => {
      if (autoRefreshRef.current !== null) clearInterval(autoRefreshRef.current);
    };
  }, [anyRunning, refreshVms]);

  useEffect(() => {
    void refreshVms();
    void syncFirewall();
  }, [refreshVms, syncFirewall]);

  function handleLogout() {
    void fetch("/api/auth/logout", { method: "POST" }).finally(() => {
      window.location.href = "/login";
    });
  }

  const runningCount = vms.filter((v) => v.status === "running").length;
  const archivedCount = vms.filter((v) => v.status === "archived").length;

  return (
    <>
      <Sidebar onLogout={handleLogout} />

      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center justify-between border-b border-border bg-card px-6 py-3">
          <div>
            <h1 className="text-base font-semibold">Hetzner</h1>
            <p className="text-xs text-muted-foreground">Virtual Machines</p>
          </div>
          <button
            onClick={() => void refreshVms(true)}
            disabled={refreshing}
            className="flex items-center gap-1.5 rounded-md px-3 py-1.5 text-sm font-medium text-muted-foreground hover:bg-accent hover:text-accent-foreground transition-colors disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${refreshing ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </header>

        {/* Stats strip */}
        {!loading && vms.length > 0 && (
          <div className="flex gap-6 border-b border-border bg-muted/40 px-6 py-2.5">
            <div className="flex items-center gap-2 text-sm">
              <span className="h-2 w-2 rounded-full bg-green-500" />
              <span className="font-medium">{runningCount}</span>
              <span className="text-muted-foreground">running</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="h-2 w-2 rounded-full bg-gray-400" />
              <span className="font-medium">{archivedCount}</span>
              <span className="text-muted-foreground">archived</span>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <Server className="h-3.5 w-3.5 text-muted-foreground" />
              <span className="font-medium">{vms.length}</span>
              <span className="text-muted-foreground">total</span>
            </div>
          </div>
        )}

        {/* Content */}
        <main className="flex-1 overflow-y-auto p-6 space-y-4">
          {firewallWarning && (
            <WarningBanner
              message={firewallWarning}
              onDismiss={() => setFirewallWarning(null)}
            />
          )}

          {fetchError && (
            <ErrorBanner
              message={fetchError}
              completedSteps={[]}
              onDismiss={() => setFetchError(null)}
            />
          )}

          {loading ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {[1, 2, 3].map((i) => (
                <Skeleton key={i} className="h-48 w-full rounded-xl" />
              ))}
            </div>
          ) : vms.length === 0 ? (
            <div className="flex flex-col items-center justify-center py-24 text-center">
              <Server className="h-12 w-12 text-muted-foreground/30 mb-4" />
              <p className="text-muted-foreground font-medium">No VMs found</p>
              <p className="text-sm text-muted-foreground/60 mt-1">Servers will appear here once created in Hetzner.</p>
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {vms.map((vm) => (
                <VmCard key={vm.name} vm={vm} onRefresh={() => void refreshVms()} />
              ))}
            </div>
          )}
        </main>
      </div>
    </>
  );
}

