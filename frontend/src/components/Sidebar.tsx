"use client";

import { Server, LogOut } from "lucide-react";
import { cn } from "@/lib/utils";

interface CloudProvider {
  id: string;
  name: string;
  available: boolean;
}

const providers: CloudProvider[] = [
  { id: "hetzner", name: "Hetzner", available: true },
  { id: "aws", name: "AWS", available: false },
  { id: "gcp", name: "Google Cloud", available: false },
];

interface SidebarProps {
  activeProvider?: string;
  onLogout: () => void;
}

export function Sidebar({ activeProvider = "hetzner", onLogout }: SidebarProps) {
  return (
    <aside className="flex h-screen w-56 flex-col border-r border-border bg-card text-card-foreground">
      {/* Logo / Brand */}
      <div className="flex flex-col gap-1 px-4 py-4 border-b border-border bg-[#0f1221]">
        <img src="/border-logo.svg" alt="Border Cloud" className="h-5 w-auto object-contain [filter:brightness(0)_invert(1)]" />
        <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-blue-400 pl-0.5">Cloud</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        <p className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          Cloud Providers
        </p>
        {providers.map((provider) => (
          <button
            key={provider.id}
            disabled={!provider.available}
            className={cn(
              "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
              provider.available
                ? activeProvider === provider.id
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
                : "cursor-not-allowed opacity-40 text-muted-foreground"
            )}
          >
            <Server className="h-4 w-4 shrink-0" />
            {provider.name}
            {!provider.available && (
              <span className="ml-auto text-[10px] font-medium uppercase tracking-wide border border-border rounded px-1 py-0.5">
                Soon
              </span>
            )}
          </button>
        ))}
      </nav>

      {/* Footer */}
      <div className="border-t border-border px-3 py-3">
        <button
          onClick={onLogout}
          className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium text-muted-foreground hover:bg-destructive/10 hover:text-destructive transition-colors"
        >
          <LogOut className="h-4 w-4" />
          Logout
        </button>
      </div>
    </aside>
  );
}
