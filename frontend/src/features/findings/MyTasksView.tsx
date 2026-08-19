import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { listMyTasks, type MyTask, type FindingSeverity, type FindingStatus } from '../../lib/api/findings';
import { ApiError } from '../../lib/api/client';
import { AlertTriangle, Clock, ClipboardList, RefreshCw } from 'lucide-react';

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

//: Same severity badge palette FindingListView.tsx (Task 3) uses, so a
//: finding reads identically whether seen inside its project or here.
const SEVERITY_CLASSES: Record<FindingSeverity, string> = {
  critical: 'text-critical border-critical/40 bg-critical/10',
  high: 'text-high border-high/40 bg-high/10',
  medium: 'text-medium border-medium/40 bg-medium/10',
  low: 'text-low border-low/40 bg-low/10',
};

function truncate(value: string, max = 80): string {
  if (!value) return '—';
  return value.length > max ? `${value.slice(0, max)}…` : value;
}

export const MyTasksView: React.FC = () => {
  const [tasks, setTasks] = useState<MyTask[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState<FindingStatus | ''>('');
  const [severityFilter, setSeverityFilter] = useState<FindingSeverity | ''>('');
  const [overdueOnly, setOverdueOnly] = useState(false);

  const load = useCallback(() => {
    setIsLoading(true);
    listMyTasks({
      status: statusFilter || undefined,
      severity: severityFilter || undefined,
      overdue: overdueOnly ? true : undefined,
    })
      .then((page) => {
        setTasks(page.items);
        setErrorMsg(null);
      })
      .catch((err) => setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải danh sách công việc.'))
      .finally(() => setIsLoading(false));
  }, [statusFilter, severityFilter, overdueOnly]);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <div className="space-y-4" data-testid="my-tasks-view">
      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Công việc của tôi</h2>
        <p className="text-xs text-text-secondary mt-1">
          Mọi phát hiện được gán cho bạn, trên tất cả các dự án.
        </p>
      </div>

      <div className="flex flex-wrap gap-2 items-center">
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
        <label className="flex items-center gap-1.5 text-xs text-text-secondary cursor-pointer select-none">
          <input
            type="checkbox"
            checked={overdueOnly}
            onChange={(event) => setOverdueOnly(event.target.checked)}
            data-testid="my-tasks-overdue-toggle"
          />
          Chỉ quá hạn
        </label>
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-text-muted" data-testid="my-tasks-loading">
          <RefreshCw className="h-6 w-6 animate-spin text-primary" />
        </div>
      ) : errorMsg ? (
        <div className="flex flex-col items-center justify-center py-16 gap-3 text-text-muted" data-testid="my-tasks-error">
          <AlertTriangle className="h-8 w-8 text-critical" />
          <p className="text-xs text-text-secondary">{errorMsg}</p>
        </div>
      ) : tasks.length === 0 ? (
        <div
          className="flex flex-col items-center justify-center py-16 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl"
          data-testid="my-tasks-empty"
        >
          <ClipboardList className="h-10 w-10 opacity-30" />
          <p className="text-xs italic">Bạn chưa được gán phát hiện nào.</p>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-xs text-left border-collapse font-mono">
            <thead>
              <tr className="border-b border-surface-container-highest text-[9px] text-text-muted uppercase tracking-widest">
                <th className="py-2 px-3">Dự án</th>
                <th className="py-2 px-3">Phát hiện</th>
                <th className="py-2 px-3">Mức độ</th>
                <th className="py-2 px-3">Trạng thái</th>
                <th className="py-2 px-3">Hạn chót</th>
                <th className="py-2 px-3">Tác động</th>
              </tr>
            </thead>
            <tbody>
              {tasks.map((task) => (
                <tr
                  key={task.id}
                  className="border-b border-surface-container-highest/45 hover:bg-surface-container/50"
                  data-testid={`my-task-row-${task.id}`}
                >
                  <td className="py-2.5 px-3">
                    <Link to={`/projects/${task.project_id}`} className="text-text-secondary hover:text-primary">
                      {task.project_name}
                    </Link>
                  </td>
                  <td className="py-2.5 px-3">
                    <Link
                      to={`/projects/${task.project_id}/findings/${task.id}`}
                      className="text-text-primary hover:text-primary"
                    >
                      {task.title}
                    </Link>
                  </td>
                  <td className="py-2.5 px-3">
                    <span className={`px-2 py-0.5 rounded border text-[10px] uppercase ${SEVERITY_CLASSES[task.severity]}`}>
                      {task.severity}
                    </span>
                  </td>
                  <td className="py-2.5 px-3 text-text-secondary">{task.status}</td>
                  <td className="py-2.5 px-3">
                    {task.is_overdue ? (
                      <span
                        className="inline-flex items-center gap-1 px-2 py-0.5 rounded border border-critical/40 bg-critical/10 text-critical text-[10px] uppercase"
                        data-testid={`my-task-overdue-badge-${task.id}`}
                      >
                        <Clock className="h-3 w-3" />
                        Quá hạn
                      </span>
                    ) : task.deadline ? (
                      new Date(task.deadline).toLocaleDateString()
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="py-2.5 px-3 text-text-secondary" title={task.impact}>
                    {truncate(task.impact)}
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

export default MyTasksView;
