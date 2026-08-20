import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  archiveProjectAsAdmin,
  listAdminProjects,
  type AdminProjectItem,
} from '../../../lib/api/adminLifecycle';
import type { ProjectCriticality, ProjectEnvironment, ProjectStatus } from '../../../lib/api/projects';
import { ApiError } from '../../../lib/api/client';
import { AdminConsoleNav } from '../components/AdminConsoleNav';
import { Archive, AlertTriangle, RefreshCw, ShieldAlert, Users } from 'lucide-react';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; items: AdminProjectItem[]; total: number };

const ENVIRONMENTS: Array<ProjectEnvironment | 'all'> = ['all', 'development', 'staging', 'production'];
const CRITICALITIES: Array<ProjectCriticality | 'all'> = ['all', 'low', 'medium', 'high', 'critical'];
const STATUSES: Array<ProjectStatus | 'all'> = ['all', 'active', 'archived'];

const CRITICALITY_CLASSES: Record<ProjectCriticality, string> = {
  critical: 'text-critical border-critical/40 bg-critical/10',
  high: 'text-high border-high/40 bg-high/10',
  medium: 'text-medium border-medium/40 bg-medium/10',
  low: 'text-low border-low/40 bg-low/10',
};

/** Task 7: every project in the system regardless of the caller's
 * membership, filterable, with an admin-only archive bypass per row - see
 * backend/api/admin_lifecycle.py's GET/POST /api/admin/projects*. */
export const AdminProjectsView: React.FC = () => {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [environment, setEnvironment] = useState<ProjectEnvironment | 'all'>('all');
  const [criticality, setCriticality] = useState<ProjectCriticality | 'all'>('all');
  const [status, setStatus] = useState<ProjectStatus | 'all'>('all');
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);
  const [pendingArchiveId, setPendingArchiveId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      const result = await listAdminProjects({
        page,
        pageSize,
        environment: environment === 'all' ? undefined : environment,
        criticality: criticality === 'all' ? undefined : criticality,
        status: status === 'all' ? undefined : status,
      });
      setState({ status: 'ready', items: result.items, total: result.total });
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof ApiError ? err.message : 'Cannot connect to backend.',
      });
    }
  }, [criticality, environment, page, pageSize, status]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [criticality, environment, status]);

  const handleArchive = async (project: AdminProjectItem) => {
    setPendingArchiveId(project.id);
    setActionError(null);
    try {
      await archiveProjectAsAdmin(project.id);
      await load();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Cannot archive project.');
    } finally {
      setPendingArchiveId(null);
    }
  };

  const total = state.status === 'ready' ? state.total : 0;
  const maxPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-6">
      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Control Console</h2>
        <p className="text-xs text-text-secondary">Every project across every workspace, with member and open-finding counts.</p>
      </div>
      <AdminConsoleNav />

      {actionError && (
        <div className="bg-critical/10 border border-critical/30 rounded-lg p-3 text-xs text-critical">{actionError}</div>
      )}

      <div className="bg-surface-container border border-surface-container-highest rounded-lg p-4 grid grid-cols-1 sm:grid-cols-3 gap-3">
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Environment</span>
          <select value={environment} onChange={(event) => setEnvironment(event.target.value as ProjectEnvironment | 'all')} className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
            {ENVIRONMENTS.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Criticality</span>
          <select value={criticality} onChange={(event) => setCriticality(event.target.value as ProjectCriticality | 'all')} className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
            {CRITICALITIES.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
        <label className="space-y-1">
          <span className="text-[10px] uppercase font-mono text-text-muted">Status</span>
          <select value={status} onChange={(event) => setStatus(event.target.value as ProjectStatus | 'all')} className="w-full bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
            {STATUSES.map((item) => <option key={item} value={item}>{item}</option>)}
          </select>
        </label>
      </div>

      {state.status === 'loading' && (
        <div className="flex items-center justify-center py-16 text-text-muted">
          <RefreshCw className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}
      {state.status === 'error' && (
        <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
          <AlertTriangle className="h-8 w-8 text-critical" />
          <p className="text-sm text-text-secondary">Cannot load projects: {state.message}</p>
          <button onClick={load} className="flex items-center gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary px-4 py-2 rounded-lg text-xs font-bold">
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      )}

      {state.status === 'ready' && (
        <div className="overflow-x-auto bg-surface-container border border-surface-container-highest rounded-lg">
          <table className="w-full text-left text-xs font-mono min-w-[980px]">
            <thead>
              <tr className="border-b border-surface-container-highest text-text-muted text-[10px] uppercase">
                <th className="py-2.5 px-4">Name</th>
                <th className="py-2.5 px-4">Environment</th>
                <th className="py-2.5 px-4">Criticality</th>
                <th className="py-2.5 px-4">Internet-facing</th>
                <th className="py-2.5 px-4">Status</th>
                <th className="py-2.5 px-4">Members</th>
                <th className="py-2.5 px-4">Open findings</th>
                <th className="py-2.5 px-4 text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-highest/40 text-text-secondary">
              {state.items.map((project) => (
                <tr key={project.id} data-testid={`admin-project-row-${project.id}`}>
                  <td className="py-3 px-4">
                    <Link to={`/projects/${project.id}`} className="text-text-primary font-bold hover:text-primary">
                      {project.name}
                    </Link>
                  </td>
                  <td className="py-3 px-4">{project.environment}</td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-0.5 rounded border text-[10px] uppercase ${CRITICALITY_CLASSES[project.criticality]}`}>
                      {project.criticality}
                    </span>
                  </td>
                  <td className="py-3 px-4">{project.internet_facing ? 'Yes' : 'No'}</td>
                  <td className="py-3 px-4">
                    <span className={project.status === 'active' ? 'text-primary' : 'text-text-muted'}>{project.status.toUpperCase()}</span>
                  </td>
                  <td className="py-3 px-4"><span className="inline-flex items-center gap-1"><Users className="h-3.5 w-3.5" /> {project.member_count}</span></td>
                  <td className="py-3 px-4"><span className="inline-flex items-center gap-1"><ShieldAlert className="h-3.5 w-3.5" /> {project.open_findings_count}</span></td>
                  <td className="py-3 px-4 text-right">
                    <button
                      disabled={project.status === 'archived' || pendingArchiveId === project.id}
                      onClick={() => handleArchive(project)}
                      className="inline-flex items-center gap-1.5 border border-surface-container-highest rounded px-2.5 py-1.5 text-[10px] uppercase hover:bg-surface-container-highest disabled:opacity-40"
                    >
                      <Archive className="h-3.5 w-3.5" />
                      {pendingArchiveId === project.id ? 'Archiving...' : 'Archive'}
                    </button>
                  </td>
                </tr>
              ))}
              {state.items.length === 0 && (
                <tr><td colSpan={8} className="py-10 text-center text-text-muted">No projects match the current filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-text-secondary">
        <div>Page {page} of {maxPage} · {total} projects</div>
        <div className="flex items-center gap-2">
          <button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="border border-surface-container-highest rounded px-3 py-1 disabled:opacity-40">Prev</button>
          <button disabled={page >= maxPage} onClick={() => setPage((value) => Math.min(maxPage, value + 1))} className="border border-surface-container-highest rounded px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
};

export default AdminProjectsView;
