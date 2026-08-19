import React, { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import {
  getEffectiveSlaPolicies,
  setProjectSlaOverride,
  type EffectiveSlaPolicy,
} from '../../lib/api/slaPolicies';
import type { FindingSeverity } from '../../lib/api/findings';
import { ApiError } from '../../lib/api/client';
import { AlertTriangle, RefreshCw, ShieldCheck } from 'lucide-react';

/**
 * Task 3 scope: a functional, standalone SLA policy view for one project -
 * shows the effective policy per severity (project override if set, else
 * the global default, else "no SLA") and lets an owner/security member set
 * or clear the project's own override. Task 7 integrates this into the
 * Admin Console's SLA/Policies tab (global-default editing there) - this
 * view intentionally does not attempt that global-admin surface, only the
 * per-project one the brief calls for here.
 */
export const SlaPolicyView: React.FC = () => {
  const params = useParams<{ id: string }>();
  const projectId = params.id;

  const [policies, setPolicies] = useState<EffectiveSlaPolicy[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [savingSeverity, setSavingSeverity] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const load = useCallback(() => {
    if (!projectId) return;
    setIsLoading(true);
    getEffectiveSlaPolicies(projectId)
      .then((rows) => {
        setPolicies(rows);
        setDrafts(
          Object.fromEntries(rows.map((row) => [row.severity, String(row.hours_to_deadline ?? '')])),
        );
        setErrorMsg(null);
      })
      .catch((err) => setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải chính sách SLA.'))
      .finally(() => setIsLoading(false));
  }, [projectId]);

  useEffect(() => {
    load();
  }, [load]);

  const handleSave = async (severity: FindingSeverity) => {
    if (!projectId) return;
    const raw = drafts[severity]?.trim();
    const hours = raw ? Number(raw) : null;
    if (raw && (!Number.isFinite(hours) || (hours as number) <= 0)) {
      setSaveError('Số giờ phải là số dương.');
      return;
    }
    setSavingSeverity(severity);
    setSaveError(null);
    try {
      await setProjectSlaOverride(projectId, severity, hours);
      load();
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : 'Không thể lưu chính sách SLA.');
    } finally {
      setSavingSeverity(null);
    }
  };

  if (!projectId) return null;

  return (
    <div className="space-y-4" data-testid="sla-policy-view">
      <div>
        <h2 className="text-sm font-mono font-bold text-text-primary flex items-center gap-2">
          <ShieldCheck className="h-4 w-4 text-primary" />
          Chính sách SLA của dự án
        </h2>
        <p className="text-[11px] text-text-muted mt-1">
          Số giờ tính từ lúc phát hiện được xác nhận (confirmed) đến hạn xử lý. Để trống để dùng
          mặc định toàn hệ thống; "không áp dụng" nghĩa là mức độ đó chưa có SLA nào (mặc định
          cho `low`).
        </p>
      </div>

      {saveError && <p className="text-xs text-critical">{saveError}</p>}

      {isLoading ? (
        <div className="flex items-center justify-center py-12 text-text-muted">
          <RefreshCw className="h-5 w-5 animate-spin text-primary" />
        </div>
      ) : errorMsg ? (
        <div className="flex flex-col items-center justify-center py-12 gap-2 text-text-muted">
          <AlertTriangle className="h-6 w-6 text-critical" />
          <p className="text-xs">{errorMsg}</p>
        </div>
      ) : (
        <table className="w-full text-xs text-left border-collapse font-mono">
          <thead>
            <tr className="border-b border-surface-container-highest text-[9px] text-text-muted uppercase tracking-widest">
              <th className="py-2 px-3">Mức độ</th>
              <th className="py-2 px-3">Nguồn hiện tại</th>
              <th className="py-2 px-3">Số giờ đến hạn</th>
              <th className="py-2 px-3" />
            </tr>
          </thead>
          <tbody>
            {policies.map((policy) => (
              <tr
                key={policy.severity}
                className="border-b border-surface-container-highest/45"
                data-testid={`sla-policy-row-${policy.severity}`}
              >
                <td className="py-2.5 px-3 uppercase">{policy.severity}</td>
                <td className="py-2.5 px-3 text-text-secondary">
                  {policy.source === 'project_override'
                    ? 'Riêng của dự án'
                    : policy.source === 'global_default'
                      ? 'Mặc định hệ thống'
                      : 'Không áp dụng'}
                </td>
                <td className="py-2.5 px-3">
                  <input
                    type="number"
                    min={1}
                    placeholder="mặc định / không áp dụng"
                    value={drafts[policy.severity] ?? ''}
                    onChange={(event) =>
                      setDrafts((prev) => ({ ...prev, [policy.severity]: event.target.value }))
                    }
                    className="w-40 bg-background border border-surface-container-highest rounded-lg px-2 py-1 text-xs text-text-primary focus:outline-none"
                  />
                </td>
                <td className="py-2.5 px-3">
                  <button
                    type="button"
                    disabled={savingSeverity === policy.severity}
                    onClick={() => handleSave(policy.severity)}
                    className="px-3 py-1 bg-primary text-background rounded-lg text-[10px] font-mono font-bold hover:bg-primary-container transition-all disabled:opacity-40"
                  >
                    {savingSeverity === policy.severity ? 'ĐANG LƯU...' : 'LƯU'}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
};

export default SlaPolicyView;
