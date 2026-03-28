"use client";

import { Suspense } from "react";
import { ChevronDown, LogOut, ScrollText, Server, FolderOpen, Users } from "lucide-react";
import { usePathname, useSearchParams } from "next/navigation";
import Image from "next/image";
import { useState } from "react";
import Link from "next/link";
import { useProject } from "@/context/ProjectContext";
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
  onLogout: () => void;
}

const adminItems = [
  { label: "Users", href: "/admin?s=users", section: "users", icon: Users },
  { label: "Projects", href: "/admin?s=projects", section: "projects", icon: FolderOpen },
  { label: "Logs", href: "/admin?s=logs", section: "logs", icon: ScrollText },
] as const;

function AdminNav() {
  const searchParams = useSearchParams();
  const activeSection = searchParams.get("s") ?? "users";

  return (
    <>
      {adminItems.map(({ label, href, section, icon: Icon }) => (
        <Link
          key={label}
          href={href}
          className={cn(
            "flex w-full items-center gap-3 rounded-md pl-6 pr-3 py-2 text-sm font-medium transition-colors",
            activeSection === section
              ? "bg-accent text-accent-foreground"
              : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
          )}
        >
          <Icon className="h-4 w-4 shrink-0" />
          {label}
        </Link>
      ))}
    </>
  );
}

export function Sidebar({ onLogout }: SidebarProps) {
  const pathname = usePathname();
  const { projects, selectedProject, setSelectedProject, currentUser } = useProject();
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);

  return (
    <aside className="flex h-screen w-56 flex-col border-r border-border bg-card text-card-foreground">
      {/* Logo / Brand */}
      <div className="flex flex-col gap-1 px-4 py-4 border-b border-border bg-[#0f1221]">
        <Image src="/border-logo.svg" alt="Border Cloud" width={120} height={20} className="h-5 w-auto object-contain [filter:brightness(0)_invert(1)]" />
        <p className="text-[10px] font-bold tracking-[0.2em] uppercase text-blue-400 pl-0.5">Cloud</p>
      </div>

      {/* Project selector */}
      {projects.length > 0 && (
        <div className="relative border-b border-border">
          <button
            onClick={() => setProjectMenuOpen((o) => !o)}
            className="flex w-full items-center justify-between gap-2 px-4 py-3 text-sm text-card-foreground hover:bg-accent/50 transition-colors"
          >
            <span className="truncate font-medium">{selectedProject?.name ?? "Select project"}</span>
            <ChevronDown className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", projectMenuOpen && "rotate-180")} />
          </button>
          {projectMenuOpen && (
            <div className="absolute left-0 right-0 top-full z-50 bg-card border border-border rounded-b-md shadow-lg">
              {projects.map((p) => (
                <button
                  key={p.id}
                  onClick={() => { setSelectedProject(p); setProjectMenuOpen(false); }}
                  className={cn(
                    "flex w-full items-center px-4 py-2 text-sm hover:bg-accent transition-colors",
                    p.id === selectedProject?.id && "text-primary font-semibold"
                  )}
                >
                  {p.name}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Navigation */}
      <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
        <p className="px-2 pb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
          Cloud Providers
        </p>
        {providers.map((provider) =>
          provider.available ? (
            <Link
              key={provider.id}
              href="/"
              className={cn(
                "flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium transition-colors",
                pathname === "/"
                  ? "bg-accent text-accent-foreground"
                  : "text-muted-foreground hover:bg-accent hover:text-accent-foreground"
              )}
            >
              <Server className="h-4 w-4 shrink-0" />
              {provider.name}
            </Link>
          ) : (
            <button
              key={provider.id}
              disabled
              className="flex w-full items-center gap-3 rounded-md px-3 py-2 text-sm font-medium cursor-not-allowed opacity-40 text-muted-foreground"
            >
              <Server className="h-4 w-4 shrink-0" />
              {provider.name}
              <span className="ml-auto text-[10px] font-medium uppercase tracking-wide border border-border rounded px-1 py-0.5">
                Soon
              </span>
            </button>
          )
        )}

        {/* Admin sub-navigation — superadmins only */}
        {currentUser?.is_superadmin && (
          <>
            <p className="px-2 pt-4 pb-2 text-[10px] font-semibold uppercase tracking-widest text-muted-foreground">
              Administration
            </p>
            <Suspense fallback={
              adminItems.map(({ label, icon: Icon }) => (
                <span key={label} className="flex w-full items-center gap-3 rounded-md pl-6 pr-3 py-2 text-sm font-medium text-muted-foreground">
                  <Icon className="h-4 w-4 shrink-0" />{label}
                </span>
              ))
            }>
              <AdminNav />
            </Suspense>
          </>
        )}
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

