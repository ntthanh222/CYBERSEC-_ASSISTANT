import React, { useEffect, useState } from 'react';
import { useLocation, useNavigate, useParams } from 'react-router-dom';
import {
  archiveProject,
  createProject,
  getProject,
  updateProject,
  type ProjectCriticality,
  type ProjectEnvironment,
} from '../../lib/api/projects';
import { listWorkspaces, type Workspace } from '../../lib/api/workspaces';
import { ApiError } from '../../lib/api/client';

const ENVIRONMENTS: ProjectEnvironment[] = ['development', 'staging', 'production'];
const CRITICALITIES: ProjectCriticality[] = ['low', 'medium', 'high', 'critical'];

export const ProjectFormView: React.FC = () => {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const isEditing = Boolean(id);

  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspaceId, setWorkspaceId] = useState('');
  const [name, setName] = useState('');
  const [domain, setDomain] = useState('');
  const [environment, setEnvironment] = useState<ProjectEnvironment>('development');
  const [criticality, setCriticality] = useState<ProjectCriticality>('medium');
  const [internetFacing, setInternetFacing] = useState(false);
  const [status, setStatus] = useState<'active' | 'archived'>('active');

  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(isEditing);

  useEffect(() => {
    listWorkspaces(1, 100).then((page) => setWorkspaces(page.items)).catch(() => setWorkspaces([]));
  }, []);

  useEffect(() => {
    if (!isEditing) {
      const params = new URLSearchParams(location.search);
      const preselected = params.get('workspace_id');
      if (preselected) setWorkspaceId(preselected);
      return;
    }
    if (!id) return;
    getProject(id)
      .then((project) => {
        setWorkspaceId(project.workspace_id);
        setName(project.name);
        setDomain(project.domain ?? '');
        setEnvironment(project.environment);
        setCriticality(project.criticality);
        setInternetFacing(project.internet_facing);
        setStatus(project.status);
      })
      .catch((err) => setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải dự án.'))
      .finally(() => setIsLoading(false));
  }, [id, isEditing, location.search]);

  const handleSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      if (id) {
        await updateProject(id, { name, domain: domain || null, environment, criticality, internet_facing: internetFacing });
        navigate(`/projects/${id}`);
      } else {
        const created = await createProject({
          workspace_id: workspaceId,
          name,
          domain: domain || null,
          environment,
          criticality,
          internet_facing: internetFacing,
        });
        navigate(`/projects/${created.id}`);
      }
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Không thể lưu dự án.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleArchive = async () => {
    if (!id) return;
    setIsSubmitting(true);
    setErrorMsg(null);
    try {
      await archiveProject(id);
      navigate(`/projects/${id}`);
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Không thể lưu trữ dự án.');
    } finally {
      setIsSubmitting(false);
    }
  };

  if (isLoading) {
    return <p className="text-xs text-text-muted font-mono">Đang tải...</p>;
  }

  return (
    <div className="max-w-lg space-y-6">
      <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">
        {isEditing ? 'Chỉnh sửa dự án' : 'Tạo dự án mới'}
      </h2>

      <form onSubmit={handleSubmit} className="space-y-4" data-testid="project-form">
        {!isEditing && (
          <div>
            <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">Workspace</label>
            <select
              required
              value={workspaceId}
              onChange={(event) => setWorkspaceId(event.target.value)}
              className="w-full bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
            >
              <option value="" disabled>Chọn workspace...</option>
              {workspaces.map((workspace) => (
                <option key={workspace.id} value={workspace.id}>{workspace.name}</option>
              ))}
            </select>
          </div>
        )}

        <div>
          <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">Tên dự án</label>
          <input
            type="text"
            required
            value={name}
            onChange={(event) => setName(event.target.value)}
            className="w-full bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
          />
        </div>

        <div>
          <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">Tên miền</label>
          <input
            type="text"
            value={domain}
            onChange={(event) => setDomain(event.target.value)}
            placeholder="app.example.com"
            className="w-full bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">Môi trường</label>
            <select
              value={environment}
              onChange={(event) => setEnvironment(event.target.value as ProjectEnvironment)}
              className="w-full bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
            >
              {ENVIRONMENTS.map((env) => (
                <option key={env} value={env}>{env}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">Mức độ nghiêm trọng</label>
            <select
              value={criticality}
              onChange={(event) => setCriticality(event.target.value as ProjectCriticality)}
              className="w-full bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
            >
              {CRITICALITIES.map((crit) => (
                <option key={crit} value={crit}>{crit}</option>
              ))}
            </select>
          </div>
        </div>

        <label className="flex items-center gap-2 text-xs text-text-secondary">
          <input
            type="checkbox"
            checked={internetFacing}
            onChange={(event) => setInternetFacing(event.target.checked)}
          />
          Lộ diện Internet
        </label>

        {errorMsg && <p className="text-xs text-critical">{errorMsg}</p>}

        <div className="flex gap-2">
          <button
            type="submit"
            disabled={isSubmitting}
            className="px-4 py-2 bg-primary text-background rounded-lg text-xs font-mono font-bold hover:bg-primary-container transition-all disabled:opacity-40"
          >
            {isSubmitting ? 'ĐANG LƯU...' : 'LƯU'}
          </button>
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-4 py-2 border border-surface-container-highest rounded-lg text-xs font-mono font-bold text-text-secondary hover:text-text-primary"
          >
            HỦY
          </button>
          {isEditing && status === 'active' && (
            <button
              type="button"
              onClick={handleArchive}
              disabled={isSubmitting}
              className="ml-auto px-4 py-2 border border-critical/30 text-critical rounded-lg text-xs font-mono font-bold hover:bg-critical/10 disabled:opacity-40"
              data-testid="archive-project-button"
            >
              LƯU TRỮ DỰ ÁN
            </button>
          )}
        </div>
      </form>
    </div>
  );
};

export default ProjectFormView;
