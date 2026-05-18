"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
} from "react";

import type { HetznerProject, User } from "@/types";

// Idle timeout before auto-logout (default 30 min). Must be <= backend ACCESS_TOKEN_EXPIRE_MINUTES.
const SESSION_TIMEOUT_MS =
  parseInt(process.env.NEXT_PUBLIC_SESSION_TIMEOUT_MINUTES ?? "30") * 60_000;
// Throttle: refresh the token at most once per 5 minutes of activity.
const REFRESH_THROTTLE_MS = 5 * 60_000;

interface ProjectContextValue {
  projects: HetznerProject[];
  selectedProject: HetznerProject | null;
  setSelectedProject: (project: HetznerProject) => void;
  currentUser: User | null;
  isLoading: boolean;
  refresh: () => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function ProjectProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<HetznerProject[]>([]);
  const [selectedProject, setSelectedProject] = useState<HetznerProject | null>(null);
  const [currentUser, setCurrentUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const sessionExpiresAt = useRef<number>(Date.now() + SESSION_TIMEOUT_MS);
  const lastRefreshAt = useRef<number>(0);

  const performLogout = useCallback(async () => {
    if (window.location.pathname === "/login") return;
    await fetch("/api/auth/logout", { method: "POST" }).catch(() => {});
    window.location.href = "/login";
  }, []);

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const [projectsRes, userRes] = await Promise.all([
        fetch("/api/projects"),
        fetch("/api/auth/me"),
      ]);

      if (projectsRes.status === 401 || userRes.status === 401) {
        await performLogout();
        return;
      }

      if (!projectsRes.ok || !userRes.ok) {
        setProjects([]);
        setSelectedProject(null);
        setCurrentUser(null);
        return;
      }

      const projectsData = (await projectsRes.json()) as { projects: HetznerProject[] };
      const userData = (await userRes.json()) as User;

      setProjects(projectsData.projects);
      setCurrentUser(userData);
      setSelectedProject((prev) => {
        const stillExists = projectsData.projects.find((p) => p.id === prev?.id);
        return stillExists ?? projectsData.projects[0] ?? null;
      });
    } catch {
      // Network error — silently ignore
    } finally {
      setIsLoading(false);
    }
  }, [performLogout]);

  const refreshToken = useCallback(async () => {
    const now = Date.now();
    if (now - lastRefreshAt.current < REFRESH_THROTTLE_MS) return;
    lastRefreshAt.current = now;
    try {
      const res = await fetch("/api/auth/refresh", { method: "POST" });
      if (res.status === 401) {
        await performLogout();
      }
    } catch {
      // Network error — ignore
    }
  }, [performLogout]);

  const handleActivity = useCallback(() => {
    sessionExpiresAt.current = Date.now() + SESSION_TIMEOUT_MS;
    void refreshToken();
  }, [refreshToken]);

  useEffect(() => {
    refresh();
  }, [refresh]);

  // Reset idle timer and refresh token on user activity.
  useEffect(() => {
    const events = ["click", "keydown", "mousemove", "scroll", "touchstart"] as const;
    events.forEach((e) => window.addEventListener(e, handleActivity, { passive: true }));
    return () => events.forEach((e) => window.removeEventListener(e, handleActivity));
  }, [handleActivity]);

  // Poll every 30 s — redirect to login if the idle timeout has been exceeded.
  useEffect(() => {
    const timer = setInterval(() => {
      if (Date.now() > sessionExpiresAt.current) {
        void performLogout();
      }
    }, 30_000);
    return () => clearInterval(timer);
  }, [performLogout]);

  // When the user returns to a backgrounded tab, check immediately.
  useEffect(() => {
    function onVisibility() {
      if (!document.hidden && Date.now() > sessionExpiresAt.current) {
        void performLogout();
      }
    }
    document.addEventListener("visibilitychange", onVisibility);
    return () => document.removeEventListener("visibilitychange", onVisibility);
  }, [performLogout]);

  return (
    <ProjectContext.Provider
      value={{ projects, selectedProject, setSelectedProject, currentUser, isLoading, refresh }}
    >
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) {
    throw new Error("useProject must be used inside <ProjectProvider>");
  }
  return ctx;
}
