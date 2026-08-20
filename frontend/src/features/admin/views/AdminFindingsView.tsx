import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listAdminFindings, type AdminFindingItem } from '../../../lib/api/adminLifecycle';
import { ApiError } from '../../../lib/api/client';
import { AdminConsoleNav } from '../components/AdminConsoleNav';
import { AlertTriangle, Clock, RefreshCw, ShieldAlert } from 'lucide-react';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; items: AdminFindingItem[]; total: number };

/** The requirement's named Admin Findings sub-views, each a filter preset
 * on the one GET /api/admin/findings endpoint - see
 * backend/api/admin_lifecycle.py's docstring for the exact query params
 * each maps to. */
type ViewKey =
  | 'open'
  | 'critical'
  | 'high'
  | 'overdue'
  | 'waiting_verify'
  | 'fixed_this_week'
  | 'accepted_risk'
  | 'false_positive';

const VIEWS: Array<{ key: ViewKey; label: string }> = [
  { key: 'open', label: 'Open' },
  { key: 'critical', label: 'Critical' },
  { key: 'high', label: 'High' },
  { key: 'overdue', label: 'Overdue' },
  { key: 'waiting_verify', label: 'Waiting Verify' },
  { key: 'fixed_this_week', label: 'Fixed This Week' },
  { key: 'accepted_risk', label: 'Accepted Risk' },
  { key: 'false_positive', label: 'False Positive' },
];

const SEVERITY_CLASSES: Record<string, string> = {
  critical: 'text-critical border-critical/40 bg-critical/10',
  high: 'text-high border-high/40 bg-high/10',
  medium: 'text-medium border-medium/40 bg-medium/10',
  low: 'text-low border-low/40 bg-low/10',
};

export const AdminFindingsView: React.FC = () => {
  const [view, setView] = useState<ViewKey>('open');
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [page, setPage] = useState(1);
  const [pageSize] = useState(25);

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      const filters =
        view === 'open'
          ? { status: 'open' as const }
          : view === 'critical'
            ? { severity: 'critical' as const }
            : view === 'high'
              ? { severity: 'high' as const }
              : view === 'overdue'
                ? { overdue: true }
                : view === 'waiting_verify'
                  ? { status: 'fixed' as const }
                  : view === 'fixed_this_week'
                    ? { preset: 'fixed_this_week' as const }
                    : view === 'accepted_risk'
                      ? { status: 'accepted_risk' as const }
                      : { status: 'false_positive' as const };
      const result = await listAdminFindings({ ...filters, page, pageSize });
      setState({ status: 'ready', items: result.items, total: result.total });
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof ApiError ? err.message : 'Cannot connect to backend.',
      });
    }
  }, [page, pageSize, view]);

  useEffect(() => {
    load();
  }, [load]);

  useEffect(() => {
    setPage(1);
  }, [view]);

  const total = state.status === 'ready' ? state.total : 0;
  const maxPage = Math.max(1, Math.ceil(total / pageSize));

  return (
    <div className="space-y-6">
      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Control Console</h2>
        <p className="text-xs text-text-secondary">Findings across every project - named views are filter presets on one endpoint.</p>
      </div>
      <AdminConsoleNav />

      <div className="flex flex-wrap gap-1.5 border-b border-surface-container-highest/60 pb-3">
        {VIEWS.map((item) => (
          <button
            key={item.key}
            onClick={() => setView(item.key)}
            data-testid={`admin-findings-view-${item.key}`}
            className={`px-3 py-1.5 rounded text-[10px] font-mono uppercase font-bold border ${
              view === item.key
                ? 'border-primary text-primary bg-primary/10'
                : 'border-surface-container-highest text-text-secondary hover:text-text-primary'
            }`}
          >
            {item.label}
          </button>
        ))}
      </div>

      {state.status === 'loading' && (
        <div className="flex items-center justify-center py-16 text-text-muted">
          <RefreshCw className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}
      {state.status === 'error' && (
        <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
          <AlertTriangle className="h-8 w-8 text-critical" />
          <p className="text-sm text-text-secondary">Cannot load findings: {state.message}</p>
          <button onClick={load} className="flex items-center gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary px-4 py-2 rounded-lg text-xs font-bold">
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      )}

      {state.status === 'ready' && (
        <div className="overflow-x-auto bg-surface-container border border-surface-container-highest rounded-lg">
          <table className="w-full text-left text-xs font-mono min-w-[920px]">
            <thead>
              <tr className="border-b border-surface-container-highest text-text-muted text-[10px] uppercase">
                <th className="py-2.5 px-4">Project</th>
                <th className="py-2.5 px-4">Title</th>
                <th className="py-2.5 px-4">Severity</th>
                <th className="py-2.5 px-4">Status</th>
                <th className="py-2.5 px-4">Assignee</th>
                <th className="py-2.5 px-4">Deadline</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-highest/40 text-text-secondary">
              {state.items.map((finding) => (
                <tr key={finding.id} data-testid={`admin-finding-row-${finding.id}`}>
                  <td className="py-3 px-4 text-text-primary">{finding.project_name}</td>
                  <td className="py-3 px-4">
                    <Link
                      to={`/projects/${finding.project_id}/findings/${finding.id}`}
                      className="text-text-primary hover:text-primary"
                    >
                      {finding.title}
                    </Link>
                  </td>
                  <td className="py-3 px-4">
                    <span className={`px-2 py-0.5 rounded border text-[10px] uppercase ${SEVERITY_CLASSES[finding.severity]}`}>
                      {finding.severity}
                    </span>
                  </td>
                  <td className="py-3 px-4">{finding.status}</td>
                  <td className="py-3 px-4">{finding.assignee_user_id ?? '—'}</td>
                  <td className="py-3 px-4">
                    {finding.is_overdue ? (
                      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-critical/40 bg-critical/10 text-critical text-[10px] uppercase">
                        <Clock className="h-3 w-3" /> Overdue
                      </span>
                    ) : finding.deadline ? (
                      new Date(finding.deadline).toLocaleDateString()
                    ) : (
                      '—'
                    )}
                  </td>
                </tr>
              ))}
              {state.items.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-text-muted">
                    <div className="flex flex-col items-center gap-2">
                      <ShieldAlert className="h-8 w-8 opacity-30" />
                      No findings in this view.
                    </div>
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-text-secondary">
        <div>Page {page} of {maxPage} · {total} findings</div>
        <div className="flex items-center gap-2">
          <button disabled={page <= 1} onClick={() => setPage((value) => Math.max(1, value - 1))} className="border border-surface-container-highest rounded px-3 py-1 disabled:opacity-40">Prev</button>
          <button disabled={page >= maxPage} onClick={() => setPage((value) => Math.min(maxPage, value + 1))} className="border border-surface-container-highest rounded px-3 py-1 disabled:opacity-40">Next</button>
        </div>
      </div>
    </div>
  );
};

export default AdminFindingsView;
