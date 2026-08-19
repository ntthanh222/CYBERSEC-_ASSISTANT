import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listProjects, type Project } from '../../lib/api/projects';
import { listWorkspaces, type Workspace } from '../../lib/api/workspaces';
import { ApiError } from '../../lib/api/client';
import { AlertTriangle, Plus, RefreshCw, FolderKanban, Globe, Archive } from 'lucide-react';

const CRIT_CHIP: Record<string, string> = {
  critical: 'bg-critical/10 text-critical border-critical/20',
  high: 'bg-high/10 text-high border-high/20',
  medium: 'bg-warning/10 text-warning border-warning/20',
  low: 'bg-success/10 text-success border-success/20',
};

export const ProjectListView: React.FC = () => {
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[]>([]);
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceFilter, setWorkspaceFilter] = useState<string>('all');
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  useEffect(() => {
    listWorkspaces(1, 100).then((page) => setWorkspaces(page.items)).catch(() => setWorkspaces([]));
  }, []);

  const fetchProjects = useCallback(() => {
    setIsLoading(true);
    listProjects({ workspaceId: workspaceFilter === 'all' ? undefined : workspaceFilter, pageSize: 100 })
      .then((page) => {
        setProjects(page.items);
        setErrorMsg(null);
      })
      .catch((err) => {
        setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải danh sách dự án.');
      })
      .finally(() => setIsLoading(false));
  }, [workspaceFilter]);

  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Dự án</h2>
          <p className="text-xs text-text-secondary">Phạm vi cho quy trình quét, phát hiện và xử lý lỗ hổng.</p>
        </div>
        <button
          onClick={() => navigate('/projects/new')}
          className="flex items-center gap-1.5 px-3 py-2 bg-primary text-background rounded-lg text-xs font-mono font-bold hover:bg-primary-container transition-all"
          data-testid="create-project-button"
        >
          <Plus className="h-4 w-4" />
          TẠO DỰ ÁN
        </button>
      </div>

      <div className="flex gap-2 items-center">
        <select
          value={workspaceFilter}
          onChange={(event) => setWorkspaceFilter(event.target.value)}
          className="bg-background border border-surface-container-highest rounded-lg px-2.5 py-1.5 text-[10px] font-mono font-bold text-text-primary focus:outline-none"
        >
          <option value="all">TẤT CẢ WORKSPACE</option>
          {workspaces.map((workspace) => (
            <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl" data-testid="project-list-loading">
          <RefreshCw className="h-8 w-8 animate-spin text-primary" />
          <p className="text-xs font-mono uppercase tracking-widest">Đang tải dự án...</p>
        </div>
      ) : errorMsg ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl" data-testid="project-list-error">
          <AlertTriangle className="h-10 w-10 text-critical" />
          <p className="text-xs text-text-secondary">{errorMsg}</p>
        </div>
      ) : projects.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl" data-testid="project-list-empty">
          <FolderKanban className="h-10 w-10 opacity-30" />
          <p className="text-xs italic">Chưa có dự án nào.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {projects.map((project) => (
            <button
              key={project.id}
              onClick={() => navigate(`/projects/${project.id}`)}
              className="text-left bg-surface-container border border-surface-container-highest rounded-xl p-4 space-y-2 hover:bg-surface-container-high/40 transition-all"
              data-testid={`project-card-${project.id}`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <FolderKanban className="h-4 w-4 text-primary" />
                  <span className="font-headline font-bold text-sm text-text-primary">{project.name}</span>
                </div>
                {project.status === 'archived' && <Archive className="h-3.5 w-3.5 text-text-muted" />}
              </div>
              {project.domain && <p className="text-[10px] font-mono text-text-muted">{project.domain}</p>}
              <div className="flex items-center gap-2">
                <span className={`px-2 py-0.5 rounded text-[9px] font-bold border capitalize ${CRIT_CHIP[project.criticality] ?? ''}`}>
                  {project.criticality}
                </span>
                <span className="text-[9px] text-text-muted uppercase">{project.environment}</span>
                {project.internet_facing && <Globe className="h-3 w-3 text-high" />}
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default ProjectListView;
