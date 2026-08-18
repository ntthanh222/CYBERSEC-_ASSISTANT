import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, ClipboardList, RefreshCw, Search } from 'lucide-react';
import {
  createIncident,
  listIncidents,
  type IncidentRecord,
  type IncidentSeverity,
  type IncidentStatus,
} from '../../../lib/api/incidents';

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

export const IncidentListView: React.FC = () => {
  const [items, setItems] = useState<IncidentRecord[]>([]);
  const [search, setSearch] = useState('');
  const [severity, setSeverity] = useState<IncidentSeverity | 'all'>('all');
  const [status, setStatus] = useState<IncidentStatus | 'all'>('all');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [form, setForm] = useState({
    title: '',
    description: '',
    severity: 'high' as IncidentSeverity,
    assignee: '',
    asset_name: '',
  });

  const load = useCallback(() => {
    setIsLoading(true);
    setError('');
    listIncidents({
      search: search.trim() || undefined,
      severity: severity === 'all' ? undefined : severity,
      status: status === 'all' ? undefined : status,
    })
      .then((page) => setItems(page.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải danh sách sự cố.'))
      .finally(() => setIsLoading(false));
  }, [search, severity, status]);

  useEffect(load, [load]);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setError('');
    try {
      await createIncident({
        title: form.title,
        description: form.description || form.title,
        severity: form.severity,
        assignee: form.assignee,
        asset_name: form.asset_name,
      });
      setForm({ title: '', description: '', severity: 'high', assignee: '', asset_name: '' });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể tạo sự cố.');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Không gian sự cố</h2>
          <p className="text-xs text-text-secondary">Các hồ sơ xử lý, nhiệm vụ phân tích và ghi chú dòng thời gian đang hoạt động.</p>
        </div>
        <div className="text-[10px] font-mono text-text-muted text-right">
          <span className="block">{items.length} INCIDENTS</span>
          <span className="text-primary">DỮ LIỆU TRỰC TIẾP</span>
        </div>
      </div>

      <form onSubmit={handleCreate} className="grid grid-cols-1 lg:grid-cols-6 gap-2 rounded-lg border border-surface-container-highest bg-surface-container p-3">
        <input required value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="Tiêu đề sự cố" className="lg:col-span-2 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Mô tả" className="lg:col-span-1 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value as IncidentSeverity })} className="bg-background border border-surface-container-highest rounded px-2 py-2 text-xs">
          <option value="critical">Nghiêm trọng</option>
          <option value="high">Cao</option>
          <option value="medium">Trung bình</option>
          <option value="low">Thấp</option>
        </select>
        <input value={form.assignee} onChange={(e) => setForm({ ...form, assignee: e.target.value })} placeholder="Người phụ trách" className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <button className="bg-primary text-background rounded px-3 py-2 text-xs font-bold">Tạo sự cố</button>
      </form>

      <div className="flex flex-wrap gap-3 items-center">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <input aria-label="Tìm kiếm sự cố" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tìm kiếm sự cố" className="w-full pl-9 pr-3 py-2 bg-background border border-surface-container-highest rounded-lg text-xs" />
        </div>
        <button onClick={load} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-surface-container-highest text-xs"><RefreshCw className="h-3.5 w-3.5" /> Làm mới</button>
        <select value={severity} onChange={(e) => setSeverity(e.target.value as IncidentSeverity | 'all')} className="bg-background border border-surface-container-highest rounded px-2 py-2 text-xs">
          <option value="all">Tất cả mức độ</option>
          <option value="critical">Nghiêm trọng</option>
          <option value="high">Cao</option>
          <option value="medium">Trung bình</option>
          <option value="low">Thấp</option>
        </select>
        <select value={status} onChange={(e) => setStatus(e.target.value as IncidentStatus | 'all')} className="bg-background border border-surface-container-highest rounded px-2 py-2 text-xs">
          <option value="all">Tất cả trạng thái</option>
          <option value="open">Mở</option>
          <option value="triaged">Đã phân loại</option>
          <option value="in_progress">Đang xử lý</option>
          <option value="contained">Đã kiểm soát</option>
          <option value="eradicated">Đã loại bỏ</option>
          <option value="recovered">Đã khôi phục</option>
          <option value="closed">Đã đóng</option>
        </select>
      </div>

      {error && <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical"><AlertTriangle className="h-4 w-4" />{error}</div>}

      {isLoading ? <div className="py-12 text-center text-xs text-text-muted">Đang tải sự cố...</div> : items.length === 0 ? (
        <div className="py-12 text-center text-xs text-text-muted border border-dashed border-surface-container-highest rounded-lg">Không có sự cố nào khớp với bộ lọc hiện tại.</div>
      ) : (
        <div className="space-y-3">
          {items.map((incident) => (
            <Link key={incident.id} to={`/incidents/${incident.id}`} className="flex items-start gap-4 p-4 bg-surface-container border border-surface-container-highest rounded-lg hover:bg-surface-container-high/50 group" data-testid={`incident-row-${incident.id}`}>
              <ClipboardList className="h-5 w-5 text-primary shrink-0 mt-1" />
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="font-bold text-text-primary group-hover:text-primary">{incident.title}</span>
                  <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${SEVERITY_CHIP[incident.severity] ?? ''}`}>{SEVERITY_LABEL[incident.severity] ?? incident.severity.toUpperCase()}</span>
                  <span className="text-[9px] font-mono text-text-muted uppercase">{incident.status.replace('_', ' ')}</span>
                </div>
                <p className="text-xs text-text-muted truncate mt-1">{incident.description}</p>
                <p className="text-[10px] text-text-muted mt-2">{incident.assignee || 'Chưa phân công'} - {incident.asset_name || 'Chưa gắn tài sản'}</p>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
};

export default IncidentListView;
