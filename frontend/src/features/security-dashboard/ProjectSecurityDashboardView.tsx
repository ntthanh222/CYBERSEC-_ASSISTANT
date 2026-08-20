import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  getProjectDashboard,
  type ProjectSecurityDashboard,
} from '../../lib/api/projectDashboard';
import type { FindingSeverity } from '../../lib/api/findings';
import { ApiError } from '../../lib/api/client';
import { AlertTriangle, Clock, RefreshCw, ShieldCheck, UserCheck } from 'lucide-react';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; dashboard: ProjectSecurityDashboard };

const SEVERITY_CLASSES: Record<FindingSeverity, string> = {
  critical: 'text-critical border-critical/40 bg-critical/10',
  high: 'text-high border-high/40 bg-high/10',
  medium: 'text-medium border-medium/40 bg-medium/10',
  low: 'text-low border-low/40 bg-low/10',
};

function scoreColorClass(score: number): string {
  if (score >= 80) return 'text-primary';
  if (score >= 50) return 'text-medium';
  return 'text-critical';
}

function formatDateTime(iso: string | null): string {
  if (!iso) return '—';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString();
}

interface MetricCardProps {
  label: string;
  value: number;
  testId: string;
  accentClass?: string;
}

const MetricCard: React.FC<MetricCardProps> = ({ label, value, testId, accentClass }) => (
  <div
    className="bg-surface-container border border-surface-container-highest rounded-xl p-4"
    data-testid={testId}
  >
    <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">
      {label}
    </span>
    <h3 className={`font-headline font-black text-2xl mt-1 ${accentClass ?? 'text-text-primary'}`}>
      {value}
    </h3>
  </div>
);

interface ProjectSecurityDashboardViewProps {
  projectId: string;
}

export const ProjectSecurityDashboardView: React.FC<ProjectSecurityDashboardViewProps> = ({
  projectId,
}) => {
  const [state, setState] = useState<LoadState>({ status: 'loading' });

  const load = useCallback(() => {
    setState({ status: 'loading' });
    getProjectDashboard(projectId)
      .then((dashboard) => setState({ status: 'ready', dashboard }))
      .catch((err) =>
        setState({
          status: 'error',
          message: err instanceof ApiError ? err.message : 'Không thể tải dashboard bảo mật.',
        }),
      );
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  if (state.status === 'loading') {
    return (
      <div
        className="flex items-center justify-center py-16 text-text-muted"
        data-testid="security-dashboard-loading"
      >
        <RefreshCw className="h-6 w-6 animate-spin text-primary" />
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div
        className="flex flex-col items-center justify-center gap-3 py-16 text-text-muted"
        data-testid="security-dashboard-error"
      >
        <AlertTriangle className="h-8 w-8 text-critical" />
        <p className="text-xs text-text-secondary">{state.message}</p>
        <button
          onClick={load}
          className="flex items-center gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary font-headline px-3 py-2 rounded-lg text-xs font-bold"
        >
          <RefreshCw className="h-3.5 w-3.5" />
          Thử lại
        </button>
      </div>
    );
  }

  const { dashboard } = state;
  const maxTrendCount = Math.max(1, ...dashboard.security_trend.map((point) => point.open_count));

  return (
    <div className="space-y-6" data-testid="security-dashboard">
      {/* Security Score */}
      <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5 flex items-center justify-between">
        <div>
          <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">
            Điểm bảo mật
          </span>
          <p className="text-[10px] text-text-muted mt-1">
            100 - min(100, critical×15 + high×8 + medium×3 + low×1)
          </p>
        </div>
        <div
          className={`font-headline font-black text-5xl ${scoreColorClass(dashboard.security_score)}`}
          data-testid="security-score"
        >
          {dashboard.security_score}
          <span className="text-lg text-text-muted">/100</span>
        </div>
      </div>

      {/* Metric cards */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        <MetricCard label="Đang mở" value={dashboard.open_findings} testId="metric-open-findings" />
        <MetricCard
          label="Nghiêm trọng"
          value={dashboard.open_by_severity.critical}
          testId="metric-critical"
          accentClass="text-critical"
        />
        <MetricCard
          label="Cao"
          value={dashboard.open_by_severity.high}
          testId="metric-high"
          accentClass="text-high"
        />
        <MetricCard label="Chờ xác minh" value={dashboard.waiting_verify} testId="metric-waiting-verify" />
        <MetricCard
          label="Quá hạn"
          value={dashboard.overdue}
          testId="metric-overdue"
          accentClass="text-critical"
        />
        <MetricCard
          label="Đã fix (7 ngày)"
          value={dashboard.fixed_this_week}
          testId="metric-fixed-this-week"
          accentClass="text-primary"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Latest scan */}
        <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5" data-testid="latest-scan-summary">
          <h3 className="font-headline font-bold text-sm text-text-primary mb-3">Lượt quét gần nhất</h3>
          {dashboard.latest_scan ? (
            <div className="space-y-1 text-xs font-mono text-text-secondary">
              <p>
                Trạng thái: <span className="text-text-primary uppercase">{dashboard.latest_scan.status}</span>
              </p>
              <p>Mục tiêu: <span className="text-text-primary">{dashboard.latest_scan.target}</span></p>
              <p>Hoàn tất: {formatDateTime(dashboard.latest_scan.completed_at)}</p>
            </div>
          ) : (
            <p className="text-xs text-text-muted italic">Chưa có lượt quét nào.</p>
          )}
        </div>

        {/* Assigned work */}
        <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5" data-testid="assigned-work-summary">
          <h3 className="font-headline font-bold text-sm text-text-primary mb-3 flex items-center gap-2">
            <UserCheck className="h-4 w-4 text-primary" />
            Công việc đã giao ({dashboard.assigned_open})
          </h3>
          {dashboard.assigned_open_by_assignee.length === 0 ? (
            <p className="text-xs text-text-muted italic">Chưa có phát hiện nào được giao.</p>
          ) : (
            <ul className="space-y-1 text-xs font-mono text-text-secondary">
              {dashboard.assigned_open_by_assignee.map((row) => (
                <li key={row.assignee_user_id} className="flex justify-between">
                  <span className="truncate">{row.assignee_user_id}</span>
                  <span className="text-text-primary font-bold">{row.open_count}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* Security trend */}
      <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5" data-testid="security-trend">
        <h3 className="font-headline font-bold text-sm text-text-primary mb-3">Xu hướng bảo mật</h3>
        {dashboard.security_trend.length === 0 ? (
          <p className="text-xs text-text-muted italic">Chưa có đủ lượt quét để hiển thị xu hướng.</p>
        ) : (
          <div className="flex items-end gap-2 h-24">
            {dashboard.security_trend.map((point) => (
              <div
                key={point.scan_run_id}
                className="flex-1 flex flex-col items-center justify-end gap-1"
                data-testid={`trend-point-${point.scan_run_id}`}
                title={`${formatDateTime(point.completed_at)} — score ${point.score}, open ${point.open_count}`}
              >
                <span className="text-[9px] font-mono text-text-muted">{point.score}</span>
                <div
                  className="w-full bg-primary/60 rounded-t"
                  style={{ height: `${Math.max(4, (point.open_count / maxTrendCount) * 60)}px` }}
                />
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Top risks */}
        <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5" data-testid="top-risks-list">
          <h3 className="font-headline font-bold text-sm text-text-primary mb-3 flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-critical" />
            Rủi ro hàng đầu
          </h3>
          {dashboard.top_risks.length === 0 ? (
            <p className="text-xs text-text-muted italic">Không có phát hiện nào đang mở.</p>
          ) : (
            <ul className="space-y-2">
              {dashboard.top_risks.map((finding) => (
                <li key={finding.id} data-testid={`top-risk-${finding.id}`}>
                  <Link
                    to={`/projects/${projectId}/findings/${finding.id}`}
                    className="flex items-center justify-between gap-2 text-xs hover:text-primary"
                  >
                    <span className="flex items-center gap-2 truncate">
                      <span className={`px-1.5 py-0.5 rounded border text-[9px] uppercase ${SEVERITY_CLASSES[finding.severity]}`}>
                        {finding.severity}
                      </span>
                      <span className="truncate text-text-primary">{finding.title}</span>
                    </span>
                    {finding.is_overdue && <Clock className="h-3 w-3 text-critical shrink-0" />}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>

        {/* Latest findings */}
        <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5" data-testid="latest-findings-list">
          <h3 className="font-headline font-bold text-sm text-text-primary mb-3">Phát hiện mới nhất</h3>
          {dashboard.latest_findings.length === 0 ? (
            <p className="text-xs text-text-muted italic">Chưa có phát hiện nào.</p>
          ) : (
            <ul className="space-y-2">
              {dashboard.latest_findings.map((finding) => (
                <li key={finding.id} data-testid={`latest-finding-${finding.id}`}>
                  <Link
                    to={`/projects/${projectId}/findings/${finding.id}`}
                    className="flex items-center justify-between gap-2 text-xs hover:text-primary"
                  >
                    <span className="flex items-center gap-2 truncate">
                      <span className={`px-1.5 py-0.5 rounded border text-[9px] uppercase ${SEVERITY_CLASSES[finding.severity]}`}>
                        {finding.severity}
                      </span>
                      <span className="truncate text-text-primary">{finding.title}</span>
                    </span>
                    <span className="text-[10px] text-text-muted shrink-0">{finding.status}</span>
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProjectSecurityDashboardView;
