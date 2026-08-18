import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { changeUserRole, getAdminAuditLog, listAdminUsers, setUserActive } from '../../../lib/api/admin';
import type { AdminAuditItem, AdminUserItem, AdminUserPage } from '../../../lib/api/admin';
import type { AppRole } from '../../../lib/api/auth';
import { ApiError } from '../../../lib/api/client';
import { useAuth } from '../../auth/AuthContext';
import { AdminConsoleNav } from '../components/AdminConsoleNav';
import { Eye, MoreHorizontal, RotateCw, Search, ShieldCheck, ShieldOff, X } from 'lucide-react';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; page: AdminUserPage };

const roles: Array<AppRole | 'all'> = ['all', 'user', 'security_analyst', 'admin', 'super_admin'];
const statuses = ['all', 'active', 'disabled'] as const;
const sources = ['all', 'demo', 'test', 'local', 'hosted'] as const;

const roleLabel = (role: AppRole | 'all') => (role === 'all' ? 'All roles' : role.replace('_', ' '));
const formatDate = (value: string | null) => (value ? new Date(value).toLocaleString() : 'Never');

export const UserManagementView: React.FC = () => {
  const { user: currentUser } = useAuth();
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [searchText, setSearchText] = useState('');
  const [search, setSearch] = useState('');
  const [role, setRole] = useState<AppRole | 'all'>('all');
  const [status, setStatus] = useState<(typeof statuses)[number]>('all');
  const [source, setSource] = useState<(typeof sources)[number]>('all');
  const [hideTestAccounts, setHideTestAccounts] = useState(true);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [selected, setSelected] = useState<AdminUserItem | null>(null);
  const [selectedAudit, setSelectedAudit] = useState<AdminAuditItem[]>([]);
  const [openMenu, setOpenMenu] = useState<string | null>(null);
  const [pendingAction, setPendingAction] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      const result = await listAdminUsers({
        page,
        pageSize,
        search,
        role,
        status,
        source,
        hideTestAccounts,
      });
      setState({ status: 'ready', page: result });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Cannot connect to backend.';
      setState({ status: 'error', message });
    }
  }, [hideTestAccounts, page, pageSize, role, search, source, status]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [hideTestAccounts, pageSize, role, search, source, status]);

  const summary = useMemo(() => {
    const items = state.status === 'ready' ? state.page.items : [];
    return {
      admins: items.filter((item) => item.role === 'admin' || item.role === 'super_admin').length,
      active: items.filter((item) => item.is_active).length,
      disabled: items.filter((item) => !item.is_active).length,
      tests: items.filter((item) => item.is_test_account).length,
    };
  }, [state]);

  const withAction = async (userId: string, action: () => Promise<unknown>) => {
    setPendingAction(userId);
    setActionError(null);
    try {
      await action();
      await load();
      if (selected?.user_id === userId) {
        const refreshed = await listAdminUsers({ page: 1, pageSize: 1, search: userId, hideTestAccounts: false });
        setSelected(refreshed.items[0] ?? null);
        const audit = await getAdminAuditLog({ targetUserId: userId, pageSize: 8 });
        setSelectedAudit(audit.items);
      }
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Action failed.');
    } finally {
      setPendingAction(null);
      setOpenMenu(null);
    }
  };

  const openDetails = async (item: AdminUserItem) => {
    setSelected(item);
    setOpenMenu(null);
    try {
      const audit = await getAdminAuditLog({ targetUserId: item.user_id, pageSize: 8 });
      setSelectedAudit(audit.items);
    } catch {
      setSelectedAudit([]);
    }
  };

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
        <p className="text-xs text-text-secondary">DB-backed administration for identities, roles, account state, and audit history.</p>
      </div>
      <AdminConsoleNav />

      {actionError && (
        <div className="bg-critical/10 border border-critical/30 rounded-lg p-3 text-xs text-critical">
          {actionError}
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        <div className="bg-surface-container border border-surface-container-highest rounded-lg p-4">
          <div className="text-[10px] uppercase font-mono text-text-muted">Visible users</div>
          <div className="text-2xl font-black text-text-primary">{total}</div>
        </div>
        <div className="bg-surface-container border border-surface-container-highest rounded-lg p-4">
          <div className="text-[10px] uppercase font-mono text-text-muted">Admin tier</div>
          <div className="text-2xl font-black text-text-primary">{summary.admins}</div>
        </div>
        <div className="bg-surface-container border border-surface-container-highest rounded-lg p-4">
          <div className="text-[10px] uppercase font-mono text-text-muted">Active / disabled</div>
          <div className="text-2xl font-black text-text-primary">{summary.active} / {summary.disabled}</div>
        </div>
        <div className="bg-surface-container border border-surface-container-highest rounded-lg p-4">
          <div className="text-[10px] uppercase font-mono text-text-muted">Test accounts shown</div>
          <div className="text-2xl font-black text-text-primary">{summary.tests}</div>
        </div>
      </div>

      <form onSubmit={applySearch} className="bg-surface-container border border-surface-container-highest rounded-lg p-4 grid grid-cols-1 lg:grid-cols-[1.5fr_repeat(4,1fr)_auto] gap-3 items-end">
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Search</span>
          <div className="flex items-center gap-2 bg-background border border-surface-container-highest rounded px-3 py-2">
            <Search className="h-4 w-4 text-text-muted" />
            <input value={searchText} onChange={(event) => setSearchText(event.target.value)} className="w-full bg-transparent outline-none text-xs text-text-primary" placeholder="Email, username, user id" />
          </div>
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Role</span>
          <select value={role} onChange={(event) => setRole(event.target.value as AppRole | 'all')} className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
            {roles.map((item) => <option key={item} value={item}>{roleLabel(item)}</option>)}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Status</span>
          <select value={status} onChange={(event) => setStatus(event.target.value as (typeof statuses)[number])} className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
            {statuses.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Source</span>
          <select value={source} onChange={(event) => setSource(event.target.value as (typeof sources)[number])} className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
            {sources.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="flex items-center gap-2 text-xs text-text-secondary">
          <input type="checkbox" checked={hideTestAccounts} onChange={(event) => setHideTestAccounts(event.target.checked)} />
          Hide TEST
        </label>
        <button type="submit" className="bg-primary text-background rounded px-4 py-2 text-xs font-bold">Apply</button>
      </form>

      {state.status === 'loading' && <div className="p-4 text-xs text-text-muted font-mono">Loading users...</div>}
      {state.status === 'error' && (
        <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
          <p className="text-sm text-text-secondary">Cannot load users: {state.message}</p>
          <button onClick={load} className="flex items-center gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary px-4 py-2 rounded-lg text-xs font-bold">
            <RotateCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      )}

      {state.status === 'ready' && (
        <div className="overflow-x-auto bg-surface-container border border-surface-container-highest rounded-lg">
          <table className="w-full text-left text-xs font-mono min-w-[920px]">
            <thead>
              <tr className="border-b border-surface-container-highest text-text-muted text-[10px] uppercase">
                <th className="py-2.5 px-4">Identity</th>
                <th className="py-2.5 px-4">Role</th>
                <th className="py-2.5 px-4">Status</th>
                <th className="py-2.5 px-4">Source</th>
                <th className="py-2.5 px-4">Last login</th>
                <th className="py-2.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-highest/40 text-text-secondary">
              {state.page.items.map((item) => {
                const isSelf = item.user_id === currentUser?.id;
                const isPending = pendingAction === item.user_id;
                return (
                  <tr key={item.user_id}>
                    <td className="py-3 px-4">
                      <button onClick={() => openDetails(item)} className="text-left">
                        <div className="text-text-primary font-bold">{item.username ?? item.email ?? item.user_id}</div>
                        <div className="text-[10px] text-text-muted break-all">{item.email ?? item.user_id}</div>
                        {isSelf && <div className="text-[9px] text-primary uppercase">Current session</div>}
                      </button>
                    </td>
                    <td className="py-3 px-4"><span className="px-2 py-0.5 rounded border border-surface-container-highest uppercase text-[9px]">{item.role}</span></td>
                    <td className="py-3 px-4"><span className={item.is_active ? 'text-primary' : 'text-text-muted'}>{item.is_active ? 'ACTIVE' : 'DISABLED'}</span></td>
                    <td className="py-3 px-4"><span className={item.is_test_account ? 'text-warning' : 'text-text-secondary'}>{item.source}{item.is_test_account ? ' / TEST' : ''}</span></td>
                    <td className="py-3 px-4 text-[10px] text-text-muted">{formatDate(item.last_login_at)}</td>
                    <td className="py-3 px-4 text-right relative">
                      <button
                        aria-label={`Actions for ${item.email ?? item.user_id}`}
                        onClick={() => setOpenMenu(openMenu === item.user_id ? null : item.user_id)}
                        className="inline-flex items-center justify-center border border-surface-container-highest rounded p-1.5 hover:bg-surface-container-highest"
                      >
                        <MoreHorizontal className="h-4 w-4" />
                      </button>
                      {openMenu === item.user_id && (
                        <div className="absolute right-4 z-20 mt-2 w-48 bg-background border border-surface-container-highest rounded-lg shadow-xl p-1 text-left">
                          <button onClick={() => openDetails(item)} className="w-full flex items-center gap-2 px-3 py-2 hover:bg-surface-container-high text-xs"><Eye className="h-3.5 w-3.5" /> Details</button>
                          <button disabled={isPending} onClick={() => withAction(item.user_id, () => changeUserRole(item.user_id, item.role === 'admin' ? 'user' : 'admin'))} className="w-full px-3 py-2 hover:bg-surface-container-high text-xs text-left disabled:opacity-40">
                            {item.role === 'admin' ? 'Demote to user' : 'Promote to admin'}
                          </button>
                          <button disabled={isPending} onClick={() => withAction(item.user_id, () => setUserActive(item.user_id, !item.is_active))} className="w-full flex items-center gap-2 px-3 py-2 hover:bg-surface-container-high text-xs disabled:opacity-40">
                            {item.is_active ? <ShieldOff className="h-3.5 w-3.5" /> : <ShieldCheck className="h-3.5 w-3.5" />}
                            {item.is_active ? 'Disable account' : 'Enable account'}
                          </button>
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
              {state.page.items.length === 0 && (
                <tr><td colSpan={6} className="py-10 text-center text-text-muted">No users match the current filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-text-secondary">
        <div>Page {page} of {maxPage} · {total} users</div>
        <div className="flex items-center gap-2">
          <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))} className="bg-background border border-surface-container-highest rounded px-2 py-1">
            {[10, 25, 50, 100].map((size) => <option key={size} value={size}>{size} / page</option>)}
          </select>
          <button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="border border-surface-container-highest rounded px-3 py-1 disabled:opacity-40">Prev</button>
          <button disabled={page >= maxPage} onClick={() => setPage((value) => Math.min(maxPage, value + 1))} className="border border-surface-container-highest rounded px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>

      {selected && (
        <div className="fixed inset-0 z-40 flex justify-end bg-background/60" onClick={() => setSelected(null)}>
          <aside className="h-full w-full max-w-xl bg-surface-container border-l border-surface-container-highest p-5 overflow-y-auto" onClick={(event) => event.stopPropagation()}>
            <div className="flex items-center justify-between gap-3 border-b border-surface-container-highest pb-3">
              <div>
                <h3 className="font-headline text-lg font-black text-text-primary">User detail</h3>
                <p className="text-[10px] text-text-muted break-all">{selected.user_id}</p>
              </div>
              <button aria-label="Close user detail" onClick={() => setSelected(null)} className="border border-surface-container-highest rounded p-1.5"><X className="h-4 w-4" /></button>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 py-4 text-xs">
              <div><div className="text-text-muted uppercase text-[10px]">Identity</div><div className="text-text-primary break-all">{selected.username ?? selected.email ?? selected.user_id}</div></div>
              <div><div className="text-text-muted uppercase text-[10px]">Email</div><div className="text-text-primary break-all">{selected.email ?? 'None'}</div></div>
              <div><div className="text-text-muted uppercase text-[10px]">Role</div><div className="text-text-primary">{selected.role}</div></div>
              <div><div className="text-text-muted uppercase text-[10px]">Status</div><div className="text-text-primary">{selected.is_active ? 'ACTIVE' : 'DISABLED'}</div></div>
              <div><div className="text-text-muted uppercase text-[10px]">Source</div><div className="text-text-primary">{selected.source}{selected.is_test_account ? ' / TEST' : ''}</div></div>
              <div><div className="text-text-muted uppercase text-[10px]">Last login</div><div className="text-text-primary">{formatDate(selected.last_login_at)}</div></div>
            </div>
            <div className="flex flex-wrap gap-2 pb-4">
              <button disabled={pendingAction === selected.user_id} onClick={() => withAction(selected.user_id, () => changeUserRole(selected.user_id, selected.role === 'admin' ? 'user' : 'admin'))} className="border border-surface-container-highest rounded px-3 py-2 text-xs disabled:opacity-40">
                {selected.role === 'admin' ? 'Demote to user' : 'Promote to admin'}
              </button>
              <button disabled={pendingAction === selected.user_id} onClick={() => withAction(selected.user_id, () => setUserActive(selected.user_id, !selected.is_active))} className="border border-surface-container-highest rounded px-3 py-2 text-xs disabled:opacity-40">
                {selected.is_active ? 'Disable account' : 'Enable account'}
              </button>
            </div>
            <h4 className="font-bold text-sm text-text-primary">Recent audit history</h4>
            <div className="mt-2 space-y-2">
              {selectedAudit.map((entry) => (
                <div key={entry.id} className="border border-surface-container-highest rounded-lg p-3 text-xs">
                  <div className="font-bold text-text-primary">{entry.action}</div>
                  <div className="text-[10px] text-text-muted">{new Date(entry.created_at).toLocaleString()}</div>
                </div>
              ))}
              {selectedAudit.length === 0 && <div className="text-xs text-text-muted">No recent audit rows for this user.</div>}
            </div>
          </aside>
        </div>
      )}
    </div>
  );
};
