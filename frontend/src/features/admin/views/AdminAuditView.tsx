import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { getAdminAuditLog } from '../../../lib/api/admin';
import type { AdminAuditItem, AdminAuditPage } from '../../../lib/api/admin';
import { ApiError } from '../../../lib/api/client';
import { AdminConsoleNav } from '../components/AdminConsoleNav';
import { RotateCw, Search } from 'lucide-react';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; page: AdminAuditPage };

const ACTION_LABEL: Record<string, string> = {
  role_changed: 'Role changed',
  user_activated: 'User activated',
  user_deactivated: 'User deactivated',
  admin_login: 'Admin login',
  admin_login_failed: 'Admin login failed',
  admin_bootstrap: 'Admin bootstrap',
};

const actionOptions = ['all', ...Object.keys(ACTION_LABEL)] as const;

export const AdminAuditView: React.FC = () => {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [searchText, setSearchText] = useState('');
  const [search, setSearch] = useState('');
  const [action, setAction] = useState<(typeof actionOptions)[number]>('all');
  const [actorUserId, setActorUserId] = useState('');
  const [targetUserId, setTargetUserId] = useState('');
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      const result = await getAdminAuditLog({
        page,
        pageSize,
        search,
        action: action === 'all' ? undefined : action,
        actorUserId: actorUserId.trim() || undefined,
        targetUserId: targetUserId.trim() || undefined,
      });
      setState({ status: 'ready', page: result });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Cannot connect to backend.';
      setState({ status: 'error', message });
    }
  }, [action, actorUserId, page, pageSize, search, targetUserId]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [action, actorUserId, pageSize, search, targetUserId]);

  const totals = useMemo(() => {
    const items = state.status === 'ready' ? state.page.items : [];
    return {
      mutations: items.filter((item) => item.action.includes('user') || item.action.includes('role')).length,
      logins: items.filter((item) => item.action.includes('login')).length,
    };
  }, [state]);

  const applySearch = (event: React.FormEvent) => {
    event.preventDefault();
    setSearch(searchText);
  };

  const total = state.status === 'ready' ? state.page.total : 0;
  const maxPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-6">
      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Control Console</h2>
        <p className="text-xs text-text-secondary">Audit trail for administrative role, activation, and privileged login activity.</p>
      </div>
      <AdminConsoleNav />

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="bg-surface-container border border-surface-container-highest rounded-lg p-4">
          <div className="text-[10px] uppercase font-mono text-text-muted">Matching events</div>
          <div className="text-2xl font-black text-text-primary">{total}</div>
        </div>
        <div className="bg-surface-container border border-surface-container-highest rounded-lg p-4">
          <div className="text-[10px] uppercase font-mono text-text-muted">User mutations on page</div>
          <div className="text-2xl font-black text-text-primary">{totals.mutations}</div>
        </div>
        <div className="bg-surface-container border border-surface-container-highest rounded-lg p-4">
          <div className="text-[10px] uppercase font-mono text-text-muted">Login events on page</div>
          <div className="text-2xl font-black text-text-primary">{totals.logins}</div>
        </div>
      </div>

      <form onSubmit={applySearch} className="bg-surface-container border border-surface-container-highest rounded-lg p-4 grid grid-cols-1 lg:grid-cols-[1.3fr_1fr_1fr_1fr_auto] gap-3 items-end">
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Search</span>
          <div className="flex items-center gap-2 bg-background border border-surface-container-highest rounded px-3 py-2">
            <Search className="h-4 w-4 text-text-muted" />
            <input value={searchText} onChange={(event) => setSearchText(event.target.value)} className="w-full bg-transparent outline-none text-xs text-text-primary" placeholder="Action or user id" />
          </div>
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Action</span>
          <select value={action} onChange={(event) => setAction(event.target.value as (typeof actionOptions)[number])} className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
            {actionOptions.map((item) => <option key={item} value={item}>{item === 'all' ? 'All actions' : ACTION_LABEL[item]}</option>)}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Actor ID</span>
          <input value={actorUserId} onChange={(event) => setActorUserId(event.target.value)} className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" placeholder="Optional UUID" />
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Target ID</span>
          <input value={targetUserId} onChange={(event) => setTargetUserId(event.target.value)} className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" placeholder="Optional UUID" />
        </label>
        <button type="submit" className="bg-primary text-background rounded px-4 py-2 text-xs font-bold">Apply</button>
      </form>

      {state.status === 'loading' && <div className="p-4 text-xs text-text-muted font-mono">Loading audit log...</div>}
      {state.status === 'error' && (
        <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
          <p className="text-sm text-text-secondary">Cannot load audit log: {state.message}</p>
          <button onClick={load} className="flex items-center gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary px-4 py-2 rounded-lg text-xs font-bold">
            <RotateCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      )}

      {state.status === 'ready' && (
        <div className="overflow-x-auto bg-surface-container border border-surface-container-highest rounded-lg">
          <table className="w-full text-left text-xs font-mono min-w-[900px]">
            <thead>
              <tr className="border-b border-surface-container-highest text-text-muted text-[10px] uppercase">
                <th className="py-2.5 px-4">Action</th>
                <th className="py-2.5 px-4">Actor</th>
                <th className="py-2.5 px-4">Target</th>
                <th className="py-2.5 px-4">Metadata</th>
                <th className="py-2.5 px-4">Time</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-highest/40 text-text-secondary">
              {state.page.items.map((item: AdminAuditItem) => (
                <tr key={item.id}>
                  <td className="py-3 px-4 text-text-primary font-bold">{ACTION_LABEL[item.action] ?? item.action}</td>
                  <td className="py-3 px-4 text-[10px] break-all">{item.actor_user_id ?? 'system'}</td>
                  <td className="py-3 px-4 text-[10px] break-all">{item.target_user_id ?? 'none'}</td>
                  <td className="py-3 px-4 text-[10px] max-w-sm truncate">{item.metadata ? JSON.stringify(item.metadata) : 'none'}</td>
                  <td className="py-3 px-4 text-[10px] text-text-muted">{new Date(item.created_at).toLocaleString()}</td>
                </tr>
              ))}
              {state.page.items.length === 0 && (
                <tr><td colSpan={5} className="py-10 text-center text-text-muted">No audit events match the current filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-text-secondary">
        <div>Page {page} of {maxPage} · {total} events</div>
        <div className="flex items-center gap-2">
          <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))} className="bg-background border border-surface-container-highest rounded px-2 py-1">
            {[10, 25, 50, 100].map((size) => <option key={size} value={size}>{size} / page</option>)}
          </select>
          <button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="border border-surface-container-highest rounded px-3 py-1 disabled:opacity-40">Prev</button>
          <button disabled={page >= maxPage} onClick={() => setPage((value) => Math.min(maxPage, value + 1))} className="border border-surface-container-highest rounded px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
};
