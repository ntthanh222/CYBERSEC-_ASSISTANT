import React, { useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { AlertTriangle, ArrowLeft, ShieldAlert } from 'lucide-react';
import { getAlert, setAlertStatus, type AlertRecord, type AlertStatus } from '../../../lib/api/alerts';
import { createIncident } from '../../../lib/api/incidents';

export const AlertDetailView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const [alert, setAlert] = useState<AlertRecord | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isEscalating, setIsEscalating] = useState(false);

  const load = () => {
    if (!id) return;
    setIsLoading(true);
    setError('');
    getAlert(id)
      .then(setAlert)
      .catch((err) => setError(err instanceof Error ? err.message : 'Không tìm thấy cảnh báo.'))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [id]);

  const updateStatus = async (status: AlertStatus) => {
    if (!alert) return;
    setAlert(await setAlertStatus(alert.id, status));
  };

  const escalateToIncident = async () => {
    if (!alert) return;
    setError('');
    setIsEscalating(true);
    try {
      const incident = await createIncident({
        title: `Incident: ${alert.title}`,
        description: alert.description || alert.title,
        severity: alert.severity,
        source_alert_id: alert.id,
        asset_name: alert.asset_name,
      });
      navigate(`/incidents/${incident.id}`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể nâng cấp cảnh báo này thành sự cố.');
    } finally {
      setIsEscalating(false);
    }
  };

  if (isLoading) return <div className="py-20 text-center text-xs text-text-muted">Đang tải cảnh báo...</div>;
  if (!alert) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-lg">
        <AlertTriangle className="h-10 w-10 opacity-40 text-critical" />
        <p className="text-xs">{error || 'Không tìm thấy cảnh báo.'}</p>
        <Link to="/alerts" className="text-primary text-xs hover:underline">Quay lại danh sách cảnh báo</Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link to="/alerts" className="flex items-center gap-1.5 text-text-muted hover:text-primary text-xs font-mono">
        <ArrowLeft className="h-3.5 w-3.5" /> Quay lại hàng đợi cảnh báo
      </Link>
      <div className="bg-surface-container border border-surface-container-highest rounded-lg p-6 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="font-headline font-black text-2xl text-text-primary">{alert.title}</h2>
            <p className="text-xs text-text-muted mt-1">{alert.source} · {new Date(alert.created_at).toLocaleString()}</p>
          </div>
          <div className="flex items-center gap-2">
            <select value={alert.status} onChange={(e) => updateStatus(e.target.value as AlertStatus)} className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
              <option value="new">Mới</option>
              <option value="acknowledged">Đã ghi nhận</option>
              <option value="investigating">Đang điều tra</option>
              <option value="resolved">Đã xử lý</option>
              <option value="false_positive">Báo động giả</option>
            </select>
            <button
              onClick={escalateToIncident}
              disabled={isEscalating}
              data-testid="escalate-to-incident"
              className="flex items-center gap-1.5 bg-critical text-background rounded px-3 py-2 text-xs font-bold disabled:opacity-50"
            >
              <ShieldAlert className="h-3.5 w-3.5" /> {isEscalating ? 'Đang nâng cấp...' : 'Nâng cấp thành sự cố'}
            </button>
          </div>
        </div>
        <p className="text-sm text-text-secondary leading-relaxed">{alert.description}</p>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
          <div className="bg-background border border-surface-container-highest rounded p-3">Mức độ nghiêm trọng: {alert.severity}</div>
          <div className="bg-background border border-surface-container-highest rounded p-3">Tài sản: {alert.asset_name || 'Chưa phân công'}</div>
          <div className="bg-background border border-surface-container-highest rounded p-3">IOC: {alert.ioc_value || 'Không có'}</div>
        </div>
        <div className="bg-background border border-surface-container-highest rounded p-3">
          <h3 className="text-[10px] font-mono text-text-muted uppercase font-bold mb-2">Bằng chứng</h3>
          <p className="text-xs text-text-secondary whitespace-pre-wrap">{alert.evidence || 'Chưa ghi nhận dữ liệu bằng chứng nào.'}</p>
        </div>
      </div>
      {error && <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical"><AlertTriangle className="h-4 w-4" />{error}</div>}
    </div>
  );
};

export default AlertDetailView;
