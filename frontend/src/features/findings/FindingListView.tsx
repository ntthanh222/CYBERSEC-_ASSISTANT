import React, { useCallback, useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { listFindings, type Finding, type FindingSeverity, type FindingStatus } from '../../lib/api/findings';
import { triggerScan } from '../../lib/api/scans';
import { ApiError } from '../../lib/api/client';
import { AlertTriangle, RefreshCw, ShieldAlert, Zap } from 'lucide-react';

const STATUS_OPTIONS: FindingStatus[] = [
  'open',
  'confirmed',
  'in_progress',
  'fixed',
  'verified',
  'closed',
  'false_positive',
  'accepted_risk',
  'reopened',
];
const SEVERITY_OPTIONS: FindingSeverity[] = ['low', 'medium', 'high', 'critical'];

const SEVERITY_CLASSES: Record<FindingSeverity, string> = {
  critical: 'text-critical border-critical/40 bg-critical/10',
  high: 'text-high border-high/40 bg-high/10',
  medium: 'text-medium border-medium/40 bg-medium/10',
  low: 'text-low border-low/40 bg-low/10',
};

interface FindingListViewProps {
  /** When rendered inside ProjectDetailView's Security tab, the project id
   * is already known and passed in directly. When rendered at its own
   * route (`/projects/:id/findings`), it is read from the URL instead. */
  projectId?: string;
}

export const FindingListView: React.FC<FindingListViewProps> = ({ projectId: projectIdProp }) => {
  const params = useParams<{ id: string }>();
  const projectId = projectIdProp ?? params.id;

  const [findings, setFindings] = useState<Finding[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<FindingStatus | ''>('');
  const [severityFilter, setSeverityFilter] = useState<FindingSeverity | ''>('');

  const [scanTarget, setScanTarget] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!projectId) return;
    setIsLoading(true);
    listFindings(projectId, {
      status: statusFilter || undefined,
      severity: severityFilter || undefined,
    })
      .then((page) => {
        setFindings(page.items);
        setErrorMsg(null);
      })
      .catch((err) => setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải danh sách phát hiện.'))
      .finally(() => setIsLoading(false));
  }, [projectId, statusFilter, severityFilter]);

  useEffect(() => {
    load();
  }, [load]);

  const handleRunScan = async (event: React.FormEvent) => {
    event.preventDefault();
    if (!projectId || !scanTarget) return;
    setIsScanning(true);
    setScanError(null);
    try {
      await triggerScan(projectId, scanTarget);
      setScanTarget('');
      load();
    } catch (err) {
      setScanError(err instanceof ApiError ? err.message : 'Không thể chạy quét bảo mật.');
    } finally {
      setIsScanning(false);
    }
  };

  if (!projectId) return null;

  return (
    <div className="space-y-4" data-testid="finding-list-view">
      <form onSubmit={handleRunScan} className="flex flex-wrap gap-2 items-end">
        <div className="flex-1 min-w-[240px]">
          <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">
            Mục tiêu quét (URL)
          </label>
          <input
            type="text"
            required
            placeholder="https://example.com"
            value={scanTarget}
            onChange={(event) => setScanTarget(event.target.value)}
            className="w-full bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
          />
        </div>
        <button
          type="submit"
          disabled={isScanning}
          data-testid="run-scan-button"
          className="flex items-center gap-1.5 px-3 py-2 bg-primary text-background rounded-lg text-xs font-mono font-bold hover:bg-primary-container transition-all disabled:opacity-40"
        >
          <Zap className="h-3.5 w-3.5" />
          {isScanning ? 'ĐANG QUÉT...' : 'CHẠY QUÉT'}
        </button>
      </form>
      {scanError && <p className="text-xs text-critical">{scanError}</p>}

      <div className="flex flex-wrap gap-2">
        <select
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as FindingStatus | '')}
          className="bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
        >
          <option value="">Tất cả trạng thái</option>
          {STATUS_OPTIONS.map((status) => (
            <option key={status} value={status}>{status}</option>
          ))}
        </select>
        <select
          value={severityFilter}
          onChange={(event) => setSeverityFilter(event.target.value as FindingSeverity | '')}
          className="bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
        >
          <option value="">Tất cả mức độ</option>
          {SEVERITY_OPTIONS.map((severity) => (
            <option key={severity} value={severity}>{severity}</option>
          ))}
        </select>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-text-muted" data-testid="finding-list-loading">
          <RefreshCw className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : errorMsg ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-text-muted" data-testid="finding-list-error">
          <AlertTriangle className="h-8 w-8 text-critical" />
          <p className="text-xs text-text-secondary">{errorMsg}</p>
        </div>
      ) : findings.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center py-16 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl"
          data-testid="finding-list-empty"
        >
          <ShieldAlert className="h-10 w-10 opacity-30" />
          <p className="text-xs italic">Chưa có phát hiện nào. Chạy một lượt quét để bắt đầu.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse font-mono">
            <thead>
              <tr className="border-b border-surface-container-highest text-[9px] text-text-muted uppercase tracking-widest">
                <th className="py-2 px-3">Tiêu đề</th>
                <th className="py-2 px-3">Mức độ</th>
                <th className="py-2 px-3">Trạng thái</th>
                <th className="py-2 px-3">Người phụ trách</th>
              </tr>
            </thead>
            <tbody>
              {findings.map((finding) => (
                <tr
                  key={finding.id}
                  className="border-b border-surface-container-highest/45 hover:bg-surface-container/50"
                  data-testid={`finding-row-${finding.id}`}
                >
                  <td className="py-2.5 px-3">
                    <Link
                      to={`/projects/${projectId}/findings/${finding.id}`}
                      className="text-text-primary hover:text-primary"
                    >
                      {finding.title}
                    </Link>
                  </td>
                  <td className="py-2.5 px-3">
                    <span className={`px-2 py-0.5 rounded border text-[10px] uppercase ${SEVERITY_CLASSES[finding.severity]}`}>
                      {finding.severity}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-text-secondary">{finding.status}</td>
                  <td className="py-2.5 px-3 text-text-secondary">{finding.assignee_user_id ?? '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};

export default FindingListView;
