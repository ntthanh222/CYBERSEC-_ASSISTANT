import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, RefreshCw, Search, ShieldAlert } from 'lucide-react';
import { createAlert, listAlerts, type AlertRecord, type AlertSeverity, type AlertStatus } from '../../../lib/api/alerts';
import { listAssets, type AssetRecord } from '../../../lib/api/assets';
import { listVulnerabilities, type VulnerabilityRecord } from '../../../lib/api/vulnerabilities';

const SEVERITY_CHIP: Record<string, string> = {
  critical: 'bg-critical/10 text-critical border-critical/20',
  high: 'bg-high/10 text-high border-high/20',
  medium: 'bg-warning/10 text-warning border-warning/20',
  low: 'bg-success/10 text-success border-success/20',
};

const SEVERITY_LABEL: Record<string, string> = {
  critical: 'NGHIÊM TRỌNG',
  high: 'CAO',
  medium: 'TRUNG BÌNH',
  low: 'THẤP',
};

export const AlertsView: React.FC = () => {
  const [items, setItems] = useState<AlertRecord[]>([]);
  const [search, setSearch] = useState('');
  const [severity, setSeverity] = useState<AlertSeverity | 'all'>('all');
  const [status, setStatus] = useState<AlertStatus | 'all'>('all');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [form, setForm] = useState({
    title: '',
    source: '',
    severity: 'high' as AlertSeverity,
    description: '',
    asset_id: '',
    vulnerability_id: '',
  });
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [vulnerabilities, setVulnerabilities] = useState<VulnerabilityRecord[]>([]);

  useEffect(() => {
    listAssets({ page: 1, pageSize: 100 })
      .then((page) => setAssets(page.items))
      .catch(() => setAssets([]));
    listVulnerabilities({ pageSize: 100 })
      .then((page) => setVulnerabilities(page.items))
      .catch(() => setVulnerabilities([]));
  }, []);

  const load = useCallback(() => {
    setIsLoading(true);
    setError('');
    listAlerts({
      search: search.trim() || undefined,
      severity: severity === 'all' ? undefined : severity,
      status: status === 'all' ? undefined : status,
    })
      .then((page) => setItems(page.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải danh sách cảnh báo.'))
      .finally(() => setIsLoading(false));
  }, [search, severity, status]);

  useEffect(load, [load]);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    try {
      await createAlert({
        title: form.title,
        source: form.source,
        severity: form.severity,
        description: form.description || form.title,
        asset_id: form.asset_id || null,
        vulnerability_id: form.vulnerability_id || null,
        asset_name: assets.find((a) => a.id === form.asset_id)?.name ?? '',
      });
      setForm({ title: '', source: '', severity: 'high', description: '', asset_id: '', vulnerability_id: '' });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể tạo cảnh báo.');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Hàng đợi cảnh báo</h2>
          <p className="text-xs text-text-secondary">Các sự kiện bảo mật cần được phân loại và xử lý.</p>
        </div>
        <div className="text-[10px] font-mono text-text-muted text-right">
          <span className="block">{items.length} CẢNH BÁO</span>
          <span className="text-primary">DỮ LIỆU TRỰC TIẾP</span>
        </div>
      </div>

      <form onSubmit={handleCreate} className="grid grid-cols-1 lg:grid-cols-8 gap-2 rounded-lg border border-surface-container-highest bg-surface-container p-3">
        <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Tiêu đề cảnh báo" className="lg:col-span-2 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <input required value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder="Nguồn" className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value as AlertSeverity })} className="bg-background border border-surface-container-highest rounded px-2 py-2 text-xs">
          <option value="critical">Nghiêm trọng</option>
          <option value="high">Cao</option>
          <option value="medium">Trung bình</option>
          <option value="low">Thấp</option>
        </select>
        <select value={form.asset_id} onChange={(e) => setForm({ ...form, asset_id: e.target.value })} className="bg-background border border-surface-container-highest rounded px-2 py-2 text-xs">
          <option value="">Chưa gắn tài sản</option>
          {assets.map((asset) => <option key={asset.id} value={asset.id}>{asset.name}</option>)}
        </select>
        <select value={form.vulnerability_id} onChange={(e) => setForm({ ...form, vulnerability_id: e.target.value })} className="bg-background border border-surface-container-highest rounded px-2 py-2 text-xs">
          <option value="">Chưa gắn CVE</option>
          {vulnerabilities.map((vuln) => <option key={vuln.id} value={vuln.id}>{vuln.cve_id}</option>)}
        </select>
        <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Mô tả" className="lg:col-span-1 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <button className="bg-primary text-background rounded px-3 py-2 text-xs font-bold">Thêm cảnh báo</button>
      </form>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <input aria-label="Tìm kiếm cảnh báo" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tìm kiếm cảnh báo" className="w-full pl-9 pr-3 py-2 bg-background border border-surface-container-highest rounded-lg text-xs" />
        </div>
        <button onClick={load} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-surface-container-highest text-xs"><RefreshCw className="h-3.5 w-3.5" /> Làm mới</button>
        <select value={severity} onChange={(e) => setSeverity(e.target.value as AlertSeverity | 'all')} className="bg-background border border-surface-container-highest rounded px-2 py-2 text-xs">
          <option value="all">Tất cả mức độ</option>
          <option value="critical">Nghiêm trọng</option>
          <option value="high">Cao</option>
          <option value="medium">Trung bình</option>
          <option value="low">Thấp</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value as AlertStatus | 'all')} className="bg-background border border-surface-container-highest rounded px-2 py-2 text-xs">
          <option value="all">Tất cả trạng thái</option>
          <option value="new">Mới</option>
          <option value="acknowledged">Đã ghi nhận</option>
          <option value="investigating">Đang điều tra</option>
          <option value="resolved">Đã xử lý</option>
          <option value="false_positive">Báo động giả</option>
        </select>
      </div>

      {error && <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical"><AlertTriangle className="h-4 w-4" />{error}</div>}

      {isLoading ? <div className="py-12 text-center text-xs text-text-muted">Đang tải cảnh báo...</div> : items.length === 0 ? (
        <div className="py-12 text-center text-xs text-text-muted border border-dashed border-surface-container-highest rounded-lg">Không có cảnh báo nào khớp với bộ lọc hiện tại.</div>
      ) : (
        <div className="space-y-3">
          {items.map((alert) => (
            <Link key={alert.id} to={`/alerts/${alert.id}`} className="flex items-start gap-4 p-4 bg-surface-container border border-surface-container-highest rounded-lg hover:bg-surface-container-high/50 group" data-testid={`alert-row-${alert.id}`}>
              <ShieldAlert className="h-5 w-5 text-primary shrink-0 mt-1" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-text-primary group-hover:text-primary">{alert.title}</span>
                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${SEVERITY_CHIP[alert.severity] ?? ''}`}>{SEVERITY_LABEL[alert.severity] ?? alert.severity.toUpperCase()}</span>
                  <span className="text-[9px] font-mono text-text-muted uppercase">{alert.status.replace('_', ' ')}</span>
                </div>
                <p className="text-xs text-text-muted truncate mt-1">{alert.description}</p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};

export default AlertsView;
