import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { listWorkspaces, type Workspace } from '../../lib/api/workspaces';
import { ApiError } from '../../lib/api/client';
import { AlertTriangle, Plus, RefreshCw, Building2 } from 'lucide-react';

export const WorkspaceListView: React.FC = () => {
  const navigate = useNavigate();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const fetchWorkspaces = useCallback(() => {
    setIsLoading(true);
    listWorkspaces()
      .then((page) => {
        setWorkspaces(page.items);
        setErrorMsg(null);
      })
      .catch((err) => {
        setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải danh sách workspace.');
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    fetchWorkspaces();
  }, [fetchWorkspaces]);

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Workspaces</h2>
          <p className="text-xs text-text-secondary">Nhóm dự án và thành viên theo tổ chức.</p>
        </div>
        <button
          onClick={() => navigate('/workspaces/new')}
          className="flex items-center gap-1.5 px-3 py-2 bg-primary text-background rounded-lg text-xs font-mono font-bold hover:bg-primary-container transition-all"
          data-testid="create-workspace-button"
        >
          <Plus className="h-4 w-4" />
          TẠO WORKSPACE
        </button>
      </div>

      {isLoading ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl" data-testid="workspace-list-loading">
          <RefreshCw className="h-8 w-8 animate-spin text-primary" />
          <p className="text-xs font-mono uppercase tracking-widest">Đang tải workspace...</p>
        </div>
      ) : errorMsg ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl" data-testid="workspace-list-error">
          <AlertTriangle className="h-10 w-10 text-critical" />
          <p className="text-xs text-text-secondary">{errorMsg}</p>
          <button onClick={fetchWorkspaces} className="mt-1 px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold border border-surface-container-highest text-text-secondary hover:text-text-primary">
            THỬ LẠI
          </button>
        </div>
      ) : workspaces.length === 0 ? (
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl" data-testid="workspace-list-empty">
          <Building2 className="h-10 w-10 opacity-30" />
          <p className="text-xs italic">Bạn chưa thuộc workspace nào.</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {workspaces.map((workspace) => (
            <button
              key={workspace.id}
              onClick={() => navigate(`/workspaces/${workspace.id}`)}
              className="text-left bg-surface-container border border-surface-container-highest rounded-xl p-4 space-y-2 hover:bg-surface-container-high/40 transition-all"
              data-testid={`workspace-card-${workspace.id}`}
            >
              <div className="flex items-center gap-2">
                <Building2 className="h-4 w-4 text-primary" />
                <span className="font-headline font-bold text-sm text-text-primary">{workspace.name}</span>
              </div>
              {workspace.description && (
                <p className="text-xs text-text-secondary line-clamp-2">{workspace.description}</p>
              )}
            </button>
          ))}
        </div>
      )}
    </div>
  );
};

export default WorkspaceListView;
