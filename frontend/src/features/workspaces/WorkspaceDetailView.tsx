import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate, useParams, Link } from 'react-router-dom';
import {
  addWorkspaceMember,
  changeWorkspaceMemberRole,
  getWorkspace,
  listWorkspaceMembers,
  removeWorkspaceMember,
  type Workspace,
  type WorkspaceMember,
  type WorkspaceRole,
} from '../../lib/api/workspaces';
import { ApiError } from '../../lib/api/client';
import { AlertTriangle, RefreshCw, UserPlus, Trash2 } from 'lucide-react';

const ROLE_OPTIONS: WorkspaceRole[] = ['owner', 'admin', 'member'];

export const WorkspaceDetailView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();

  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<WorkspaceMember[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [newUserId, setNewUserId] = useState('');
  const [newRole, setNewRole] = useState<WorkspaceRole>('member');
  const [isSubmitting, setIsSubmitting] = useState(false);

  const load = useCallback(() => {
    if (!id) return;
    setIsLoading(true);
    Promise.all([getWorkspace(id), listWorkspaceMembers(id)])
      .then(([workspaceRecord, memberPage]) => {
        setWorkspace(workspaceRecord);
        setMembers(memberPage.items);
        setErrorMsg(null);
      })
      .catch((err) => setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải workspace.'))
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
      await addWorkspaceMember(id, newUserId, newRole);
      setNewUserId('');
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Không thể thêm thành viên.');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleRoleChange = async (userId: string, role: WorkspaceRole) => {
    if (!id) return;
    setActionError(null);
    try {
      await changeWorkspaceMemberRole(id, userId, role);
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Không thể đổi vai trò.');
    }
  };

  const handleRemove = async (userId: string) => {
    if (!id) return;
    setActionError(null);
    try {
      await removeWorkspaceMember(id, userId);
      load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Không thể xóa thành viên.');
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted" data-testid="workspace-detail-loading">
        <RefreshCw className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (errorMsg || !workspace) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted" data-testid="workspace-detail-error">
        <AlertTriangle className="h-10 w-10 text-critical" />
        <p className="text-xs text-text-secondary">{errorMsg ?? 'Không tìm thấy workspace.'}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">{workspace.name}</h2>
          {workspace.description && <p className="text-xs text-text-secondary">{workspace.description}</p>}
        </div>
        <div className="flex gap-2">
          <Link
            to={`/workspaces/${workspace.id}/edit`}
            className="px-3 py-2 border border-surface-container-highest rounded-lg text-xs font-mono font-bold text-text-secondary hover:text-text-primary"
          >
            CHỈNH SỬA
          </Link>
          <button
            onClick={() => navigate(`/projects/new?workspace_id=${workspace.id}`)}
            className="px-3 py-2 bg-primary text-background rounded-lg text-xs font-mono font-bold hover:bg-primary-container transition-all"
          >
            TẠO DỰ ÁN
          </button>
        </div>
      </div>

      <div className="space-y-3">
        <h3 className="font-headline font-bold text-sm text-text-primary">Thành viên</h3>

        <form onSubmit={handleAddMember} className="flex flex-wrap gap-2 items-end" data-testid="add-member-form">
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
              onChange={(event) => setNewRole(event.target.value as WorkspaceRole)}
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
                <tr key={member.id} className="border-b border-surface-container-highest/45" data-testid={`workspace-member-${member.user_id}`}>
                  <td className="py-2.5 px-3 text-text-secondary">{member.user_id}</td>
                  <td className="py-2.5 px-3">
                    <select
                      value={member.workspace_role}
                      onChange={(event) => handleRoleChange(member.user_id, event.target.value as WorkspaceRole)}
                      className="bg-background border border-surface-container-highest rounded px-2 py-1 text-[10px] text-text-primary focus:outline-none"
                    >
                      {ROLE_OPTIONS.map((role) => (
                        <option key={role} value={role}>{role}</option>
                      ))}
                    </select>
                  </td>
                  <td className="py-2.5 px-3 text-right">
                    <button
                      onClick={() => handleRemove(member.user_id)}
                      className="text-critical hover:text-critical/70"
                      aria-label="Xóa thành viên"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};

export default WorkspaceDetailView;
