import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listAdminWorkspaces, type AdminWorkspaceItem } from '../../../lib/api/adminLifecycle';
import { ApiError } from '../../../lib/api/client';
import { AdminConsoleNav } from '../components/AdminConsoleNav';
import { AlertTriangle, FolderKanban, RefreshCw, Users } from 'lucide-react';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; items: AdminWorkspaceItem[]; total: number };

const formatDate = (value: string) => new Date(value).toLocaleDateString();

/** Task 7: every workspace in the system, not just ones the caller (an
 * admin) happens to belong to - see backend/api/admin_lifecycle.py's
 * GET /api/admin/workspaces. Follows UserManagementView's paginated table
 * pattern. */
export const AdminWorkspacesView: React.FC = () => {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      const result = await listAdminWorkspaces(page, pageSize);
      setState({ status: 'ready', items: result.items, total: result.total });
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof ApiError ? err.message : 'Cannot connect to backend.',
      });
    }
  }, [page, pageSize]);

  useEffect(() => {
    load();
  }, [load]);

  const total = state.status === 'ready' ? state.total : 0;
  const maxPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-6">
      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Control Console</h2>
        <p className="text-xs text-text-secondary">Every workspace across the system, with member and project counts.</p>
      </div>
      <AdminConsoleNav />

      {state.status === 'loading' && (
        <div className="flex items-center justify-center py-16 text-text-muted">
          <RefreshCw className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}
      {state.status === 'error' && (
        <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
          <AlertTriangle className="h-8 w-8 text-critical" />
          <p className="text-sm text-text-secondary">Cannot load workspaces: {state.message}</p>
          <button onClick={load} className="flex items-center gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary px-4 py-2 rounded-lg text-xs font-bold">
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      )}

      {state.status === 'ready' && (
        <div className="overflow-x-auto bg-surface-container border border-surface-container-highest rounded-lg">
          <table className="w-full text-left text-xs font-mono min-w-[720px]">
            <thead>
              <tr className="border-b border-surface-container-highest text-text-muted text-[10px] uppercase">
                <th className="py-2.5 px-4">Name</th>
                <th className="py-2.5 px-4">Members</th>
                <th className="py-2.5 px-4">Projects</th>
                <th className="py-2.5 px-4">Created</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-highest/40 text-text-secondary">
              {state.items.map((workspace) => (
                <tr key={workspace.id} data-testid={`admin-workspace-row-${workspace.id}`}>
                  <td className="py-3 px-4">
                    <Link to={`/workspaces/${workspace.id}`} className="text-text-primary font-bold hover:text-primary">
                      {workspace.name}
                    </Link>
                    {workspace.description && (
                      <div className="text-[10px] text-text-muted">{workspace.description}</div>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    <span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5" /> {workspace.member_count}</span>
                  </td>
                  <td className="py-3 px-4">
                    <span className="inline-flex items-center gap-1"><FolderKanban className="h-3.5 w-3.5" /> {workspace.project_count}</span>
                  </td>
                  <td className="py-3 px-4 text-[10px] text-text-muted">{formatDate(workspace.created_at)}</td>
                </tr>
              ))}
              {state.items.length === 0 && (
                <tr><td colSpan={4} className="py-10 text-center text-text-muted">No workspaces yet.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-text-secondary">
        <div>Page {page} of {maxPage} · {total} workspaces</div>
        <div className="flex items-center gap-2">
          <button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="border border-surface-container-highest rounded px-3 py-1 disabled:opacity-40">Prev</button>
          <button disabled={page >= maxPage} onClick={() => setPage((value) => Math.min(maxPage, value + 1))} className="border border-surface-container-highest rounded px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
};

export default AdminWorkspacesView;
