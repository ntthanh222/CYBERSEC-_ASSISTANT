import React, { useCallback, useEffect, useState } from 'react';
import { listGlobalSlaPolicies, updateGlobalSlaPolicy, type SlaPolicy } from '../../../lib/api/slaPolicies';
import type { FindingSeverity } from '../../../lib/api/findings';
import { ApiError } from '../../../lib/api/client';
import { AdminConsoleNav } from '../components/AdminConsoleNav';
import { AlertTriangle, RefreshCw, Timer } from 'lucide-react';

const SEVERITIES: FindingSeverity[] = ['critical', 'high', 'medium', 'low'];

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready' };

/** Task 7: wires the Admin Console's SLA/Policies tab to the global-default
 * SLA endpoints Task 3 already built (backend/api/sla_policies.py's
 * admin_router - GET/PATCH /api/admin/sla-policies*) - not duplicated here,
 * just given an admin-tier UI. The per-project override UI (Task 3's
 * SlaPolicyView) stays a separate, standalone page reached from a
 * project's own detail view. */
export const AdminSlaPoliciesView: React.FC = () => {
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [policies, setPolicies] = useState<SlaPolicy[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingSeverity, setSavingSeverity] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      const rows = await listGlobalSlaPolicies();
      setPolicies(rows);
      setDrafts(Object.fromEntries(rows.map((row) => [row.severity, String(row.hours_to_deadline)])));
      setState({ status: 'ready' });
    } catch (err) {
      setState({
        status: 'error',
        message: err instanceof ApiError ? err.message : 'Cannot connect to backend.',
      });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async (severity: FindingSeverity) => {
    const raw = drafts[severity]?.trim();
    const hours = Number(raw);
    if (!raw || !Number.isFinite(hours) || hours <= 0) {
      setSaveError('Hours to deadline must be a positive number.');
      return;
    }
    setSavingSeverity(severity);
    setSaveError(null);
    try {
      await updateGlobalSlaPolicy(severity, hours);
      await load();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Cannot save SLA policy.');
    } finally {
      setSavingSeverity(null);
    }
  };

  const byServerity = Object.fromEntries(policies.map((row) => [row.severity, row]));

  return (
    <div className="space-y-6">
      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Control Console</h2>
        <p className="text-xs text-text-secondary">
          Global default SLA policies - hours from "confirmed" to deadline, applied to any project without its own override.
        </p>
      </div>
      <AdminConsoleNav />

      {saveError && <div className="bg-critical/10 border border-critical/30 rounded-lg p-3 text-xs text-critical">{saveError}</div>}

      {state.status === 'loading' && (
        <div className="flex items-center justify-center py-16 text-text-muted">
          <RefreshCw className="h-6 w-6 animate-spin text-primary" />
        </div>
      )}
      {state.status === 'error' && (
        <div className="flex flex-col items-center justify-center gap-4 py-20 text-center">
          <AlertTriangle className="h-8 w-8 text-critical" />
          <p className="text-sm text-text-secondary">Cannot load SLA policies: {state.message}</p>
          <button onClick={load} className="flex items-center gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary px-4 py-2 rounded-lg text-xs font-bold">
            <RefreshCw className="h-3.5 w-3.5" /> Retry
          </button>
        </div>
      )}

      {state.status === 'ready' && (
        <div className="overflow-x-auto bg-surface-container border border-surface-container-highest rounded-lg">
          <table className="w-full text-left text-xs font-mono min-w-[560px]">
            <thead>
              <tr className="border-b border-surface-container-highest text-text-muted text-[10px] uppercase">
                <th className="py-2.5 px-4">Severity</th>
                <th className="py-2.5 px-4">Hours to deadline</th>
                <th className="py-2.5 px-4" />
              </tr>
            </thead>
            <tbody className="divide-y divide-surface-container-highest/40 text-text-secondary">
              {SEVERITIES.map((severity) => (
                <tr key={severity} data-testid={`admin-sla-row-${severity}`}>
                  <td className="py-3 px-4">
                    <span className="inline-flex items-center gap-1.5 uppercase text-text-primary font-bold">
                      <Timer className="h-3.5 w-3.5" /> {severity}
                    </span>
                    {!byServerity[severity] && (
                      <div className="text-[10px] text-text-muted">No default set yet</div>
                    )}
                  </td>
                  <td className="py-3 px-4">
                    <input
                      type="number"
                      min={1}
                      value={drafts[severity] ?? ''}
                      onChange={(event) => setDrafts((prev) => ({ ...prev, [severity]: event.target.value }))}
                      placeholder="e.g. 72"
                      className="w-32 bg-background border border-surface-container-highest rounded px-2 py-1 text-xs text-text-primary focus:outline-none"
                    />
                  </td>
                  <td className="py-3 px-4">
                    <button
                      disabled={savingSeverity === severity}
                      onClick={() => handleSave(severity)}
                      className="px-3 py-1.5 bg-primary text-background rounded text-[10px] font-mono font-bold disabled:opacity-40"
                    >
                      {savingSeverity === severity ? 'SAVING...' : 'SAVE'}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default AdminSlaPoliciesView;
