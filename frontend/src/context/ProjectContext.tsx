"use client";

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useState,
} from "react";

import type { HetznerProject, User } from "@/types";

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

  const refresh = useCallback(async () => {
    setIsLoading(true);
    try {
      const [projectsRes, userRes] = await Promise.all([
        fetch("/api/projects"),
        fetch("/api/auth/me"),
      ]);

      // Not authenticated — leave state empty; middleware handles the redirect
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
      // Keep selected project if it still exists, otherwise pick the first one
      setSelectedProject((prev) => {
        const stillExists = projectsData.projects.find((p) => p.id === prev?.id);
        return stillExists ?? projectsData.projects[0] ?? null;
      });
    } catch {
      // Network error — silently ignore
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

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
