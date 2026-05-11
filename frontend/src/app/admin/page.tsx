"use client";

import { useCallback, useEffect, useState } from "react";
import { Pencil, Plus, RefreshCw, Trash2, UserPlus, X } from "lucide-react";
import { Sidebar } from "@/components/Sidebar";
import { ErrorBanner } from "@/components/ErrorBanner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiFetch } from "@/lib/api";
import { useProject } from "@/context/ProjectContext";
import { cn } from "@/lib/utils";
import type { HetznerProject, OperationLog, User } from "@/types";

// --------------------------------------------------------------------------- //
// Types mirroring backend admin schemas
// --------------------------------------------------------------------------- //

interface PermissionOut {
  user_id: number;
  project_id: number;
  username: string;
}

// --------------------------------------------------------------------------- //
// Shared small components
// --------------------------------------------------------------------------- //

function SectionHeader({ title }: { title: string }) {
  return (
    <h2 className="text-sm font-semibold uppercase tracking-widest text-muted-foreground mb-3">
      {title}
    </h2>
  );
}

function TableWrapper({ children }: { children: React.ReactNode }) {
  return (
    <div className="overflow-x-auto rounded-lg border border-border">
      <table className="w-full text-sm">{children}</table>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Users tab
// --------------------------------------------------------------------------- //

function ProjectCheckboxes({
  projects,
  selected,
  onChange,
}: {
  projects: HetznerProject[];
  selected: Set<number>;
  onChange: (id: number, checked: boolean) => void;
}) {
  if (projects.length === 0) return <span className="text-xs text-muted-foreground">No projects available.</span>;
  return (
    <div className="flex flex-wrap gap-2">
      {projects.map((p) => (
        <label key={p.id} className="flex items-center gap-1.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={selected.has(p.id)}
            onChange={(e) => onChange(p.id, e.target.checked)}
            className="h-3.5 w-3.5 rounded border-border accent-primary"
          />
          <span className="text-xs">{p.name}</span>
        </label>
      ))}
    </div>
  );
}

function UsersTab() {
  const [users, setUsers] = useState<User[]>([]);
  const [allProjects, setAllProjects] = useState<HetznerProject[]>([]);
  const [userPerms, setUserPerms] = useState<Record<number, Set<number>>>({}); // userId → Set<projectId>
  const [error, setError] = useState<string | null>(null);

  // Create form state
  const [showForm, setShowForm] = useState(false);
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [isSuperadmin, setIsSuperadmin] = useState(false);
  const [newUserProjects, setNewUserProjects] = useState<Set<number>>(new Set());
  const [submitting, setSubmitting] = useState(false);

  // Edit state — which user row is expanded
  const [editingUserId, setEditingUserId] = useState<number | null>(null);

  const loadProjects = useCallback(async () => {
    try {
      const data = await apiFetch<HetznerProject[]>("/api/admin/projects");
      setAllProjects(data);
    } catch { /* ignore */ }
  }, []);

  const loadUsers = useCallback(async () => {
    try {
      const data = await apiFetch<User[]>("/api/admin/users");
      setUsers(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load users");
    }
  }, []);

  const loadUserPerms = useCallback(async (userId: number) => {
    try {
      // Reuse the project-users endpoint: fetch permissions per project then invert
      // Easier: fetch all permissions for this user by querying each project
      // Instead: call GET /admin/projects and for each, check /admin/projects/{id}/users
      // That's N+1 — instead we load all at once via the projects endpoint which returns all permissions for a project
      // Simplest: load perms for all projects and filter by userId
      const permsPerProject = await Promise.all(
        allProjects.map((p) =>
          apiFetch<PermissionOut[]>(`/api/admin/projects/${p.id}/users`).then((rows) =>
            rows.filter((r) => r.user_id === userId).map((r) => r.project_id)
          )
        )
      );
      const projectIds = new Set(permsPerProject.flat());
      setUserPerms((prev) => ({ ...prev, [userId]: projectIds }));
    } catch { /* ignore */ }
  }, [allProjects]);

  useEffect(() => { void loadUsers(); void loadProjects(); }, [loadUsers, loadProjects]);

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      const created = await apiFetch<User>("/api/admin/users", {
        method: "POST",
        body: JSON.stringify({ username, password, is_superadmin: isSuperadmin }),
      });
      // Grant selected project permissions
      await Promise.all(
        Array.from(newUserProjects).map((pid) =>
          apiFetch(`/api/admin/projects/${pid}/users/${created.id}`, { method: "POST" })
        )
      );
      setUsername(""); setPassword(""); setIsSuperadmin(false);
      setNewUserProjects(new Set()); setShowForm(false);
      void loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create user");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleDelete(userId: number) {
    if (!confirm("Delete this user? This cannot be undone.")) return;
    try {
      await apiFetch(`/api/admin/users/${userId}`, { method: "DELETE" });
      void loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete user");
    }
  }

  async function handleToggleSuperadmin(user: User) {
    try {
      await apiFetch(`/api/admin/users/${user.id}`, {
        method: "PUT",
        body: JSON.stringify({ is_superadmin: !user.is_superadmin }),
      });
      void loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update user");
    }
  }

  async function handleToggleActive(user: User) {
    try {
      await apiFetch(`/api/admin/users/${user.id}`, {
        method: "PUT",
        body: JSON.stringify({ is_active: !user.is_active }),
      });
      void loadUsers();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update user");
    }
  }

  function openEdit(userId: number) {
    setEditingUserId(userId);
    void loadUserPerms(userId);
  }

  function closeEdit() {
    setEditingUserId(null);
  }

  async function handlePermChange(userId: number, projectId: number, grant: boolean) {
    try {
      if (grant) {
        await apiFetch(`/api/admin/projects/${projectId}/users/${userId}`, { method: "POST" });
      } else {
        await apiFetch(`/api/admin/projects/${projectId}/users/${userId}`, { method: "DELETE" });
      }
      setUserPerms((prev) => {
        const next = new Set(prev[userId] ?? []);
        if (grant) next.add(projectId); else next.delete(projectId);
        return { ...prev, [userId]: next };
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update permissions");
    }
  }

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} completedSteps={[]} onDismiss={() => setError(null)} />}

      <div className="flex items-center justify-between">
        <SectionHeader title="Users" />
        <Button size="sm" onClick={() => { setShowForm((v) => !v); setEditingUserId(null); }}>
          {showForm ? <X className="h-4 w-4 mr-1" /> : <Plus className="h-4 w-4 mr-1" />}
          {showForm ? "Cancel" : "Add User"}
        </Button>
      </div>

      {showForm && (
        <form onSubmit={(e) => void handleCreate(e)} className="rounded-lg border border-border bg-muted/30 p-4 space-y-4">
          <div className="flex flex-wrap gap-3 items-end">
            <div className="flex-1 min-w-[160px] space-y-1">
              <label className="text-xs text-muted-foreground">Username</label>
              <Input value={username} onChange={(e) => setUsername(e.target.value)} required placeholder="alice" />
            </div>
            <div className="flex-1 min-w-[160px] space-y-1">
              <label className="text-xs text-muted-foreground">Password</label>
              <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} required placeholder="••••••••" />
            </div>
            <div className="flex items-center gap-2 pb-0.5">
              <input
                id="superadmin-cb"
                type="checkbox"
                checked={isSuperadmin}
                onChange={(e) => setIsSuperadmin(e.target.checked)}
                className="h-4 w-4 rounded border-border"
              />
              <label htmlFor="superadmin-cb" className="text-sm">Superadmin</label>
            </div>
          </div>
          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">Project access</label>
            <ProjectCheckboxes
              projects={allProjects}
              selected={newUserProjects}
              onChange={(id, checked) =>
                setNewUserProjects((prev) => {
                  const next = new Set(prev);
                  if (checked) next.add(id); else next.delete(id);
                  return next;
                })
              }
            />
          </div>
          <Button type="submit" disabled={submitting} size="sm">
            {submitting ? "Creating…" : "Create User"}
          </Button>
        </form>
      )}

      <TableWrapper>
        <thead className="bg-muted/50">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">ID</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Username</th>
            <th className="px-4 py-2 text-center text-xs font-semibold text-muted-foreground">Superadmin</th>
            <th className="px-4 py-2 text-center text-xs font-semibold text-muted-foreground">Active</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Projects</th>
            <th className="px-4 py-2" />
          </tr>
        </thead>
        <tbody>
          {users.map((user) => (
            <>
              <tr key={user.id} className="border-t border-border hover:bg-muted/20">
                <td className="px-4 py-2 text-muted-foreground">{user.id}</td>
                <td className="px-4 py-2 font-medium">{user.username}</td>
                <td className="px-4 py-2 text-center">
                  <button
                    onClick={() => void handleToggleSuperadmin(user)}
                    className={`text-xs font-medium px-2 py-0.5 rounded-full transition-colors ${user.is_superadmin ? "bg-primary/20 text-primary hover:bg-primary/30" : "bg-muted text-muted-foreground hover:bg-muted/80"}`}
                  >
                    {user.is_superadmin ? "Yes" : "No"}
                  </button>
                </td>
                <td className="px-4 py-2 text-center">
                  <button
                    onClick={() => void handleToggleActive(user)}
                    className={`text-xs font-medium px-2 py-0.5 rounded-full transition-colors ${user.is_active ? "bg-green-500/20 text-green-400 hover:bg-green-500/30" : "bg-destructive/20 text-destructive hover:bg-destructive/30"}`}
                  >
                    {user.is_active ? "Active" : "Inactive"}
                  </button>
                </td>
                <td className="px-4 py-2">
                  <button
                    onClick={() => editingUserId === user.id ? closeEdit() : openEdit(user.id)}
                    className="flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <Pencil className="h-3 w-3" />
                    {editingUserId === user.id ? "Close" : "Edit access"}
                  </button>
                </td>
                <td className="px-4 py-2 text-right">
                  <button
                    onClick={() => void handleDelete(user.id)}
                    className="text-muted-foreground hover:text-destructive transition-colors p-1 rounded"
                    title="Delete user"
                  >
                    <Trash2 className="h-4 w-4" />
                  </button>
                </td>
              </tr>
              {editingUserId === user.id && (
                <tr key={`${user.id}-perms`} className="border-t border-border bg-muted/10">
                  <td colSpan={6} className="px-6 py-3 space-y-1.5">
                    <p className="text-xs font-semibold text-muted-foreground">Project access for &ldquo;{user.username}&rdquo;</p>
                    <ProjectCheckboxes
                      projects={allProjects}
                      selected={userPerms[user.id] ?? new Set()}
                      onChange={(pid, checked) => void handlePermChange(user.id, pid, checked)}
                    />
                  </td>
                </tr>
              )}
            </>
          ))}
          {users.length === 0 && (
            <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">No users found.</td></tr>
          )}
        </tbody>
      </TableWrapper>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Projects tab
// --------------------------------------------------------------------------- //

function ProjectsTab() {
  const { refresh: refreshContext } = useProject();
  const [projects, setProjects] = useState<HetznerProject[]>([]);
  const [allUsers, setAllUsers] = useState<User[]>([]);
  const [permissions, setPermissions] = useState<Record<number, PermissionOut[]>>({});
  const [expandedProject, setExpandedProject] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [apiToken, setApiToken] = useState("");
  const [firewallName, setFirewallName] = useState("");
  const [firewallInternal, setFirewallInternal] = useState("");
  const [cloudflareZoneId, setCloudflareZoneId] = useState("");
  const [cloudflareApiToken, setCloudflareApiToken] = useState("");
  const [submitting, setSubmitting] = useState(false);

  // Edit state
  const [editingProjectId, setEditingProjectId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editApiToken, setEditApiToken] = useState("");
  const [editFirewallName, setEditFirewallName] = useState("");
  const [editFirewallInternal, setEditFirewallInternal] = useState("");
  const [editCloudflareZoneId, setEditCloudflareZoneId] = useState("");
  const [editCloudflareApiToken, setEditCloudflareApiToken] = useState("");
  const [editIsActive, setEditIsActive] = useState(true);
  const [editSubmitting, setEditSubmitting] = useState(false);

  const loadProjects = useCallback(async () => {
    try {
      const data = await apiFetch<HetznerProject[]>("/api/admin/projects");
      setProjects(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load projects");
    }
  }, []);

  const loadUsers = useCallback(async () => {
    try {
      const data = await apiFetch<User[]>("/api/admin/users");
      setAllUsers(data);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { void loadProjects(); void loadUsers(); }, [loadProjects, loadUsers]);

  async function loadPermissions(projectId: number) {
    try {
      const data = await apiFetch<PermissionOut[]>(`/api/admin/projects/${projectId}/users`);
      setPermissions((prev) => ({ ...prev, [projectId]: data }));
    } catch { /* ignore */ }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    setSubmitting(true);
    try {
      await apiFetch("/api/admin/projects", {
        method: "POST",
        body: JSON.stringify({ name, api_token: apiToken, firewall_name: firewallName, firewall_internal: firewallInternal, cloudflare_zone_id: cloudflareZoneId, cloudflare_api_token: cloudflareApiToken }),
      });
      setName(""); setApiToken(""); setFirewallName(""); setFirewallInternal(""); setCloudflareZoneId(""); setCloudflareApiToken(""); setShowForm(false);
      void loadProjects();
      void refreshContext();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create project");
    } finally {
      setSubmitting(false);
    }
  }

  async function handleUpdate(e: React.FormEvent, projectId: number) {
    e.preventDefault();
    setEditSubmitting(true);
    try {
      const body: Record<string, unknown> = {
        name: editName,
        firewall_name: editFirewallName,
        firewall_internal: editFirewallInternal,
        cloudflare_zone_id: editCloudflareZoneId,
        cloudflare_api_token: editCloudflareApiToken || undefined,
        is_active: editIsActive,
      };
      if (editApiToken) body.api_token = editApiToken;
      await apiFetch(`/api/admin/projects/${projectId}`, {
        method: "PUT",
        body: JSON.stringify(body),
      });
      setEditingProjectId(null);
      void loadProjects();
      void refreshContext();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update project");
    } finally {
      setEditSubmitting(false);
    }
  }

  function openEdit(project: HetznerProject) {
    setEditingProjectId(project.id);
    setEditName(project.name);
    setEditApiToken("");
    setEditFirewallName(project.firewall_name ?? "");
    setEditFirewallInternal(project.firewall_internal ?? "");
    setEditCloudflareZoneId(project.cloudflare_zone_id ?? "");
    setEditCloudflareApiToken("");
    setEditIsActive(project.is_active);
    setExpandedProject(null);
  }

  async function handleDelete(projectId: number) {
    if (!confirm("Delete this project? All permissions will also be removed.")) return;
    try {
      await apiFetch(`/api/admin/projects/${projectId}`, { method: "DELETE" });
      void loadProjects();
      void refreshContext();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete project");
    }
  }

  async function handleGrant(projectId: number, userId: number) {
    try {
      await apiFetch(`/api/admin/projects/${projectId}/users/${userId}`, { method: "POST" });
      void loadPermissions(projectId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to grant access");
    }
  }

  async function handleRevoke(projectId: number, userId: number) {
    try {
      await apiFetch(`/api/admin/projects/${projectId}/users/${userId}`, { method: "DELETE" });
      void loadPermissions(projectId);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to revoke access");
    }
  }

  function toggleExpand(projectId: number) {
    if (expandedProject === projectId) {
      setExpandedProject(null);
    } else {
      setExpandedProject(projectId);
      void loadPermissions(projectId);
    }
  }

  const projectPerms = expandedProject ? (permissions[expandedProject] ?? []) : [];
  const grantedUserIds = new Set(projectPerms.map((p) => p.user_id));

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} completedSteps={[]} onDismiss={() => setError(null)} />}

      <div className="flex items-center justify-between">
        <SectionHeader title="Hetzner Projects" />
        <Button size="sm" onClick={() => setShowForm((v) => !v)}>
          {showForm ? <X className="h-4 w-4 mr-1" /> : <Plus className="h-4 w-4 mr-1" />}
          {showForm ? "Cancel" : "Add Project"}
        </Button>
      </div>

      {showForm && (
        <form onSubmit={(e) => void handleCreate(e)} className="flex flex-wrap gap-3 items-end rounded-lg border border-border bg-muted/30 p-4">
          <div className="flex-1 min-w-[140px] space-y-1">
            <label className="text-xs text-muted-foreground">Name</label>
            <Input value={name} onChange={(e) => setName(e.target.value)} required placeholder="production" />
          </div>
          <div className="flex-1 min-w-[240px] space-y-1">
            <label className="text-xs text-muted-foreground">Hetzner API Token</label>
            <Input value={apiToken} onChange={(e) => setApiToken(e.target.value)} required placeholder="htz_…" />
          </div>
          <div className="flex-1 min-w-[160px] space-y-1">
            <label className="text-xs text-muted-foreground">Firewall Name (users)</label>
            <Input value={firewallName} onChange={(e) => setFirewallName(e.target.value)} placeholder="fw-users" />
          </div>
          <div className="flex-1 min-w-[160px] space-y-1">
            <label className="text-xs text-muted-foreground">Firewall Name (internal)</label>
            <Input value={firewallInternal} onChange={(e) => setFirewallInternal(e.target.value)} placeholder="fw-internal" />
          </div>
          <div className="flex-1 min-w-[200px] space-y-1">
            <label className="text-xs text-muted-foreground">Cloudflare Zone ID (optional)</label>
            <Input value={cloudflareZoneId} onChange={(e) => setCloudflareZoneId(e.target.value)} placeholder="abc123…" />
          </div>
          <div className="flex-1 min-w-[240px] space-y-1">
            <label className="text-xs text-muted-foreground">Cloudflare API Token (optional)</label>
            <Input value={cloudflareApiToken} onChange={(e) => setCloudflareApiToken(e.target.value)} placeholder="cf_…" />
          </div>
          <Button type="submit" disabled={submitting} size="sm">
            {submitting ? "Creating…" : "Create"}
          </Button>
        </form>
      )}

      <TableWrapper>
        <thead className="bg-muted/50">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">ID</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Name</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Firewall</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">CF Zone ID</th>
            <th className="px-4 py-2 text-center text-xs font-semibold text-muted-foreground">Active</th>
            <th className="px-4 py-2 text-center text-xs font-semibold text-muted-foreground">Users</th>
            <th className="px-4 py-2" />
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <>
              <tr key={project.id} className="border-t border-border hover:bg-muted/20">
                <td className="px-4 py-2 text-muted-foreground">{project.id}</td>
                <td className="px-4 py-2 font-medium">{project.name}</td>
                <td className="px-4 py-2 text-muted-foreground">{project.firewall_name || "—"}</td>
                <td className="px-4 py-2 text-muted-foreground font-mono text-xs">{project.cloudflare_zone_id || "—"}</td>
                <td className="px-4 py-2 text-center">
                  <span className={`text-xs font-medium px-2 py-0.5 rounded-full ${project.is_active ? "bg-green-500/20 text-green-400" : "bg-destructive/20 text-destructive"}`}>
                    {project.is_active ? "Active" : "Inactive"}
                  </span>
                </td>
                <td className="px-4 py-2 text-center">
                  <button
                    onClick={() => toggleExpand(project.id)}
                    className="flex items-center gap-1 mx-auto text-xs text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <UserPlus className="h-3.5 w-3.5" />
                    Manage
                  </button>
                </td>
                <td className="px-4 py-2 text-right">
                  <div className="flex items-center justify-end gap-1">
                    <button
                      onClick={() => editingProjectId === project.id ? setEditingProjectId(null) : openEdit(project)}
                      className="text-muted-foreground hover:text-foreground transition-colors p-1 rounded"
                      title="Edit project"
                    >
                      <Pencil className="h-4 w-4" />
                    </button>
                    <button
                      onClick={() => void handleDelete(project.id)}
                      className="text-muted-foreground hover:text-destructive transition-colors p-1 rounded"
                      title="Delete project"
                    >
                      <Trash2 className="h-4 w-4" />
                    </button>
                  </div>
                </td>
              </tr>
              {editingProjectId === project.id && (
                <tr key={`${project.id}-edit`} className="border-t border-border bg-muted/10">
                  <td colSpan={7} className="px-6 py-4">
                    <form onSubmit={(e) => void handleUpdate(e, project.id)} className="space-y-3">
                      <p className="text-xs font-semibold text-muted-foreground mb-2">Edit &ldquo;{project.name}&rdquo;</p>
                      <div className="flex flex-wrap gap-3 items-end">
                        <div className="flex-1 min-w-[140px] space-y-1">
                          <label className="text-xs text-muted-foreground">Name</label>
                          <Input value={editName} onChange={(e) => setEditName(e.target.value)} required />
                        </div>
                        <div className="flex-1 min-w-[240px] space-y-1">
                          <label className="text-xs text-muted-foreground">Hetzner API Token (leave blank to keep current)</label>
                          <Input type="password" value={editApiToken} onChange={(e) => setEditApiToken(e.target.value)} placeholder="••••••••" />
                        </div>
                        <div className="flex-1 min-w-[160px] space-y-1">
                          <label className="text-xs text-muted-foreground">Firewall Name (users)</label>
                          <Input value={editFirewallName} onChange={(e) => setEditFirewallName(e.target.value)} placeholder="fw-users" />
                        </div>
                        <div className="flex-1 min-w-[160px] space-y-1">
                          <label className="text-xs text-muted-foreground">Firewall Name (internal)</label>
                          <Input value={editFirewallInternal} onChange={(e) => setEditFirewallInternal(e.target.value)} placeholder="fw-internal" />
                        </div>
                        <div className="flex-1 min-w-[200px] space-y-1">
                          <label className="text-xs text-muted-foreground">Cloudflare Zone ID</label>
                          <Input value={editCloudflareZoneId} onChange={(e) => setEditCloudflareZoneId(e.target.value)} placeholder="abc123…" />
                        </div>
                        <div className="flex-1 min-w-[240px] space-y-1">
                          <label className="text-xs text-muted-foreground">Cloudflare API Token (leave blank to keep current)</label>
                          <Input type="password" value={editCloudflareApiToken} onChange={(e) => setEditCloudflareApiToken(e.target.value)} placeholder="••••••••" />
                        </div>
                        <div className="flex items-center gap-2 pb-0.5">
                          <input
                            id={`active-${project.id}`}
                            type="checkbox"
                            checked={editIsActive}
                            onChange={(e) => setEditIsActive(e.target.checked)}
                            className="h-4 w-4 rounded border-border"
                          />
                          <label htmlFor={`active-${project.id}`} className="text-sm">Active</label>
                        </div>
                      </div>
                      <div className="flex gap-2">
                        <Button type="submit" disabled={editSubmitting} size="sm">
                          {editSubmitting ? "Saving…" : "Save changes"}
                        </Button>
                        <Button type="button" variant="outline" size="sm" onClick={() => setEditingProjectId(null)}>
                          Cancel
                        </Button>
                      </div>
                    </form>
                  </td>
                </tr>
              )}
              {expandedProject === project.id && (
                <tr key={`${project.id}-perms`} className="border-t border-border bg-muted/10">
                  <td colSpan={7} className="px-6 py-3">
                    <p className="text-xs font-semibold text-muted-foreground mb-2">User access for &ldquo;{project.name}&rdquo;</p>
                    <div className="flex flex-wrap gap-2">
                      {allUsers.map((user) => {
                        const hasAccess = grantedUserIds.has(user.id);
                        return (
                          <button
                            key={user.id}
                            onClick={() => void (hasAccess ? handleRevoke(project.id, user.id) : handleGrant(project.id, user.id))}
                            className={`flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium transition-colors border ${hasAccess ? "border-primary/50 bg-primary/10 text-primary hover:bg-destructive/10 hover:text-destructive hover:border-destructive/50" : "border-border bg-muted text-muted-foreground hover:border-primary/50 hover:bg-primary/10 hover:text-primary"}`}
                          >
                            {hasAccess ? "✓" : "+"} {user.username}
                          </button>
                        );
                      })}
                      {allUsers.length === 0 && <span className="text-xs text-muted-foreground">No users to manage.</span>}
                    </div>
                  </td>
                </tr>
              )}
            </>
          ))}
          {projects.length === 0 && (
            <tr><td colSpan={7} className="px-4 py-8 text-center text-muted-foreground">No projects found.</td></tr>
          )}
        </tbody>
      </TableWrapper>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Logs tab
// --------------------------------------------------------------------------- //

function LogsTab() {
  const [logs, setLogs] = useState<OperationLog[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [vmFilter, setVmFilter] = useState("");
  const [opFilter, setOpFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");

  const statusColors: Record<string, string> = {
    done: "bg-green-500/20 text-green-400",
    error: "bg-destructive/20 text-destructive",
    "in-progress": "bg-yellow-500/20 text-yellow-400",
  };

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({ limit: "200" });
      if (vmFilter) params.set("vm_name", vmFilter);
      if (opFilter) params.set("operation", opFilter);
      if (statusFilter) params.set("status", statusFilter);
      const data = await apiFetch<{ logs: OperationLog[] }>(`/api/admin/vms/logs?${params.toString()}`);
      setLogs(data.logs);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load logs");
    } finally {
      setLoading(false);
    }
  }, [vmFilter, opFilter, statusFilter]);

  useEffect(() => { void load(); }, [load]);

  return (
    <div className="space-y-4">
      {error && <ErrorBanner message={error} completedSteps={[]} onDismiss={() => setError(null)} />}

      <div className="flex items-center justify-between">
        <SectionHeader title="VM Operation Logs" />
        <Button size="sm" variant="outline" onClick={() => void load()} disabled={loading}>
          <RefreshCw className={cn("h-3.5 w-3.5 mr-1", loading && "animate-spin")} />
          Refresh
        </Button>
      </div>

      {/* Filters */}
      <div className="flex flex-wrap gap-2">
        <Input
          value={vmFilter}
          onChange={(e) => setVmFilter(e.target.value)}
          placeholder="Filter by VM name…"
          className="h-8 text-xs w-48"
        />
        <select
          value={opFilter}
          onChange={(e) => setOpFilter(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2 text-xs"
        >
          <option value="">All operations</option>
          <option value="start">start</option>
          <option value="stop">stop</option>
          <option value="archive">archive</option>
          <option value="restore">restore</option>
          <option value="delete">delete</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="h-8 rounded-md border border-input bg-background px-2 text-xs"
        >
          <option value="">All statuses</option>
          <option value="done">done</option>
          <option value="error">error</option>
          <option value="in-progress">in-progress</option>
        </select>
      </div>

      <TableWrapper>
        <thead className="bg-muted/50">
          <tr>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Time</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">VM</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Operation</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">By</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Status</th>
            <th className="px-4 py-2 text-left text-xs font-semibold text-muted-foreground">Error</th>
          </tr>
        </thead>
        <tbody>
          {logs.map((entry) => (
            <tr key={entry.id} className="border-t border-border hover:bg-muted/20">
              <td className="px-4 py-2 font-mono text-xs text-muted-foreground whitespace-nowrap">
                {new Date(entry.started_at).toLocaleString()}
              </td>
              <td className="px-4 py-2 font-medium">{entry.vm_name}</td>
              <td className="px-4 py-2 capitalize">{entry.operation}</td>
              <td className="px-4 py-2 text-muted-foreground">{entry.initiated_by}</td>
              <td className="px-4 py-2">
                <span className={cn("text-xs font-medium px-2 py-0.5 rounded-full", statusColors[entry.status] ?? "bg-muted text-muted-foreground")}>
                  {entry.status}
                </span>
              </td>
              <td className="px-4 py-2 text-xs text-red-400 max-w-xs truncate" title={entry.error_message ?? ""}>
                {entry.error_message ?? "—"}
              </td>
            </tr>
          ))}
          {logs.length === 0 && !loading && (
            <tr><td colSpan={6} className="px-4 py-8 text-center text-muted-foreground">No log entries found.</td></tr>
          )}
        </tbody>
      </TableWrapper>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Admin page
// --------------------------------------------------------------------------- //

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";

type Section = "users" | "projects" | "logs";

function AdminSection() {
  const searchParams = useSearchParams();
  const section = (searchParams.get("s") ?? "users") as Section;
  if (section === "projects") return <ProjectsTab />;
  if (section === "logs") return <LogsTab />;
  return <UsersTab />;
}

export default function AdminPage() {
  const { currentUser } = useProject();

  function handleLogout() {
    void fetch("/api/auth/logout", { method: "POST" }).finally(() => {
      window.location.href = "/login";
    });
  }

  // Redirect non-superadmins (belt-and-suspenders; middleware/backend already guard)
  if (currentUser && !currentUser.is_superadmin) {
    return (
      <>
        <Sidebar onLogout={handleLogout} />
        <div className="flex flex-1 items-center justify-center text-muted-foreground">
          Access denied.
        </div>
      </>
    );
  }

  return (
    <>
      <Sidebar onLogout={handleLogout} />
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Top bar */}
        <header className="flex items-center border-b border-border bg-card px-6 py-3">
          <div>
            <h1 className="text-base font-semibold">Admin Panel</h1>
            <p className="text-xs text-muted-foreground">Manage users, projects and logs</p>
          </div>
        </header>

        <main className="flex-1 overflow-y-auto p-6">
          <Suspense fallback={<div className="text-muted-foreground text-sm">Loading…</div>}>
            <AdminSection />
          </Suspense>
        </main>
      </div>
    </>
  );
}
