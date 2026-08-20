import React, { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  addProjectMember,
  changeProjectMemberRole,
  getProject,
  listProjectMembers,
  removeProjectMember,
  updateProject,
  type Project,
  type ProjectMember,
  type ProjectRole,
  type Technology,
} from '../../lib/api/projects';
import { ApiError } from '../../lib/api/client';
import { AlertTriangle, RefreshCw, UserPlus, Trash2, Plus } from 'lucide-react';
import { FindingListView } from '../findings/FindingListView';
import { ProjectSecurityDashboardView } from '../security-dashboard/ProjectSecurityDashboardView';
import { ProjectCvePriorityView } from '../cve-priority/ProjectCvePriorityView';

const ROLE_OPTIONS: ProjectRole[] = ['owner', 'security', 'developer', 'viewer'];
type Tab = 'overview' | 'members' | 'technologies' | 'security';

export const ProjectDetailView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [tab, setTab] = useState<Tab>('overview');

  const [project, setProject] = useState<Project | null>(null);
  const [members, setMembers] = useState<ProjectMember[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [newUserId, setNewUserId] = useState('');
  const [newRole, setNewRole] = useState<ProjectRole>('developer');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const [techName, setTechName] = useState('');
  const [techVersion, setTechVersion] = useState('');

  const load = useCallback(() => {
    if (!id) return;
    setIsLoading(true);
    Promise.all([getProject(id), listProjectMembers(id)])
      .then(([projectRecord, memberPage]) => {
        setProject(projectRecord);
        setMembers(memberPage.items);
        setErrorMsg(null);
      })
      .catch((err) => setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải dự án.'))
      .finally(() => setIsLoading(false));
  }, [id]);

  useEffect(() => {
    load();
  }, [load]);

  const handleAddMember = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!id || !newUserId) return;
    setIsSubmitting(true);
    setActionError(null);
    try {
      await addProjectMember(id, newUserId, newRole);
      setNewUserId('');
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Không thể thêm thành viên.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRoleChange = async (userId: string, role: ProjectRole) => {
    if (!id) return;
    setActionError(null);
    try {
      await changeProjectMemberRole(id, userId, role);
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Không thể đổi vai trò.');
    }
  };

  const handleRemove = async (userId: string) => {
    if (!id) return;
    setActionError(null);
    try {
      await removeProjectMember(id, userId);
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Không thể xóa thành viên.');
    }
  };

  const handleAddTechnology = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!id || !project || !techName) return;
    const next: Technology[] = [...project.technologies, { name: techName, version: techVersion }];
    setActionError(null);
    try {
      const updated = await updateProject(id, { technologies: next });
      setProject(updated);
      setTechName('');
      setTechVersion('');
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Không thể thêm công nghệ.');
    }
  };

  const handleRemoveTechnology = async (index: number) => {
    if (!id || !project) return;
    const next = project.technologies.filter((_, i) => i !== index);
    setActionError(null);
    try {
      const updated = await updateProject(id, { technologies: next });
      setProject(updated);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Không thể xóa công nghệ.');
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted" data-testid="project-detail-loading">
        <RefreshCw className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (errorMsg || !project) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted" data-testid="project-detail-error">
        <AlertTriangle className="h-10 w-10 text-critical" />
        <p className="text-xs text-text-secondary">{errorMsg ?? 'Không tìm thấy dự án.'}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">
            {project.name}
            {project.status === 'archived' && (
              <span className="ml-2 text-[10px] align-middle px-2 py-0.5 rounded border border-surface-container-highest text-text-muted uppercase">Đã lưu trữ</span>
            )}
          </h2>
          {project.domain && <p className="text-xs text-text-secondary">{project.domain}</p>}
        </div>
        <Link
          to={`/projects/${project.id}/edit`}
          className="px-3 py-2 border border-surface-container-highest rounded-lg text-xs font-mono font-bold text-text-secondary hover:text-text-primary"
        >
          CHỈNH SỬA
        </Link>
      </div>

      <div className="flex gap-2 border-b border-surface-container-highest/40">
        {(['overview', 'members', 'technologies', 'security'] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-3 py-2 text-[10px] font-mono font-bold uppercase tracking-widest border-b-2 transition-all ${
              tab === t ? 'border-primary text-primary' : 'border-transparent text-text-muted hover:text-text-primary'
            }`}
            data-testid={`project-tab-${t}`}
          >
            {t}
          </button>
        ))}
      </div>

      {tab === 'overview' && (
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4" data-testid="project-overview">
          <Field label="Môi trường" value={project.environment} />
          <Field label="Mức độ nghiêm trọng" value={project.criticality} />
          <Field label="Lộ diện Internet" value={project.internet_facing ? 'Có' : 'Không'} />
          <Field label="Trạng thái" value={project.status} />
          <Field label="Tên miền" value={project.domain ?? '—'} />
        </div>
      )}

      {tab === 'members' && (
        <div className="space-y-3" data-testid="project-members">
          <form onSubmit={handleAddMember} className="flex flex-wrap gap-2 items-end">
            <div>
              <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">User ID</label>
              <input
                type="text"
                required
                placeholder="uuid"
                value={newUserId}
                onChange={(event) => setNewUserId(event.target.value)}
                className="bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none w-72"
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">Vai trò</label>
              <select
                value={newRole}
                onChange={(event) => setNewRole(event.target.value as ProjectRole)}
                className="bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
              >
                {ROLE_OPTIONS.map((role) => (
                  <option key={role} value={role}>{role}</option>
                ))}
              </select>
            </div>
            <button
              type="submit"
              disabled={isSubmitting}
              className="flex items-center gap-1.5 px-3 py-2 bg-primary text-background rounded-lg text-xs font-mono font-bold hover:bg-primary-container transition-all disabled:opacity-40"
            >
              <UserPlus className="h-3.5 w-3.5" />
              THÊM
            </button>
          </form>

          {actionError && <p className="text-xs text-critical">{actionError}</p>}

          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left border-collapse font-mono">
              <thead>
                <tr className="border-b border-surface-container-highest text-[9px] text-text-muted uppercase tracking-widest">
                  <th className="py-2 px-3">User ID</th>
                  <th className="py-2 px-3">Vai trò</th>
                  <th className="py-2 px-3" />
                </tr>
              </thead>
              <tbody>
                {members.map((member) => (
                  <tr key={member.id} className="border-b border-surface-container-highest/45" data-testid={`project-member-${member.user_id}`}>
                    <td className="py-2.5 px-3 text-text-secondary">{member.user_id}</td>
                    <td className="py-2.5 px-3">
                      <select
                        value={member.project_role}
                        onChange={(event) => handleRoleChange(member.user_id, event.target.value as ProjectRole)}
                        className="bg-background border border-surface-container-highest rounded px-2 py-1 text-[10px] text-text-primary focus:outline-none"
                      >
                        {ROLE_OPTIONS.map((role) => (
                          <option key={role} value={role}>{role}</option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      <button onClick={() => handleRemove(member.user_id)} className="text-critical hover:text-critical/70" aria-label="Xóa thành viên">
                        <Trash2 className="h-3.5 w-3.5" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {tab === 'technologies' && (
        <div className="space-y-3" data-testid="project-technologies">
          <form onSubmit={handleAddTechnology} className="flex flex-wrap gap-2 items-end">
            <div>
              <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">Tên</label>
              <input
                type="text"
                required
                value={techName}
                onChange={(event) => setTechName(event.target.value)}
                className="bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">Phiên bản</label>
              <input
                type="text"
                value={techVersion}
                onChange={(event) => setTechVersion(event.target.value)}
                className="bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
              />
            </div>
            <button
              type="submit"
              className="flex items-center gap-1.5 px-3 py-2 bg-primary text-background rounded-lg text-xs font-mono font-bold hover:bg-primary-container transition-all"
            >
              <Plus className="h-3.5 w-3.5" />
              THÊM
            </button>
          </form>

          {actionError && <p className="text-xs text-critical">{actionError}</p>}

          <div className="flex flex-wrap gap-2">
            {project.technologies.length === 0 ? (
              <p className="text-xs text-text-muted italic">Chưa có công nghệ nào được ghi nhận.</p>
            ) : (
              project.technologies.map((tech, index) => (
                <span
                  key={`${tech.name}-${index}`}
                  className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border border-surface-container-highest text-[10px] font-mono"
                >
                  {tech.name}{tech.version ? ` @ ${tech.version}` : ''}
                  <button onClick={() => handleRemoveTechnology(index)} className="text-critical hover:text-critical/70" aria-label="Xóa công nghệ">
                    <Trash2 className="h-3 w-3" />
                  </button>
                </span>
              ))
            )}
          </div>
        </div>
      )}

      {tab === 'security' && (
        <div className="space-y-6" data-testid="project-security">
          <ProjectSecurityDashboardView projectId={project.id} />
          <ProjectCvePriorityView projectId={project.id} />
          <FindingListView projectId={project.id} />
        </div>
      )}
    </div>
  );
};

const Field: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="bg-surface-container border border-surface-container-highest rounded-xl p-3 space-y-1">
    <span className="text-[9px] font-mono uppercase tracking-widest text-text-muted font-bold">{label}</span>
    <p className="text-xs text-text-primary capitalize">{value}</p>
  </div>
);

export default ProjectDetailView;
