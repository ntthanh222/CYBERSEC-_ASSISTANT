import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { listProjects, type Project } from '../../lib/api/projects';

interface ProjectContextValue {
  /** The currently-selected project, or null if none chosen yet. Persisted
   * to localStorage so a reload keeps the same working context - later
   * phases (Dashboard, AI Assistant) read this to scope their own views. */
  selectedProject: Project | null;
  selectProject: (project: Project | null) => void;
  projects: Project[];
  isLoading: boolean;
  refresh: () => void;
}

const STORAGE_KEY = 'cybersec.selectedProjectId';

const ProjectContext = createContext<ProjectContextValue | undefined>(undefined);

export const ProjectProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [selectedProject, setSelectedProject] = useState<Project | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const refresh = useCallback(() => {
    setIsLoading(true);
    listProjects({ pageSize: 100 })
      .then((page) => {
        setProjects(page.items);
        const storedId = window.localStorage.getItem(STORAGE_KEY);
        if (storedId) {
          const match = page.items.find((project) => project.id === storedId);
          if (match) setSelectedProject(match);
        }
      })
      .catch(() => setProjects([]))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const selectProject = useCallback((project: Project | null) => {
    setSelectedProject(project);
    if (project) {
      window.localStorage.setItem(STORAGE_KEY, project.id);
    } else {
      window.localStorage.removeItem(STORAGE_KEY);
    }
  }, []);

  return (
    <ProjectContext.Provider value={{ selectedProject, selectProject, projects, isLoading, refresh }}>
      {children}
    </ProjectContext.Provider>
  );
};

export function useSelectedProject(): ProjectContextValue {
  const context = useContext(ProjectContext);
  if (!context) {
    throw new Error('useSelectedProject must be used within a ProjectProvider');
  }
  return context;
}

/** A compact dropdown for switching the active project - consumers beyond
 * the Project pages themselves are wired up in a later phase. */
export const ProjectPicker: React.FC = () => {
  const { projects, selectedProject, selectProject, isLoading } = useSelectedProject();

  if (isLoading) {
    return <span className="text-[10px] text-text-muted font-mono">Đang tải dự án...</span>;
  }

  return (
    <select
      value={selectedProject?.id ?? ''}
      onChange={(event) => {
        const project = projects.find((item) => item.id === event.target.value) ?? null;
        selectProject(project);
      }}
      className="bg-background border border-surface-container-highest rounded-lg px-2.5 py-1.5 text-[10px] font-mono font-bold text-text-primary focus:outline-none"
      data-testid="project-picker"
    >
      <option value="">Chọn dự án...</option>
      {projects.map((project) => (
        <option key={project.id} value={project.id}>
          {project.name}
        </option>
      ))}
    </select>
  );
};
