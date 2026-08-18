import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Eye, EyeOff, RefreshCw, Search } from 'lucide-react';
import { IOCBadge } from '../components/IOCBadge';
import { IOCLayout } from '../components/IOCLayout';
import {
  createThreatIOC,
  listThreatIOCs,
  type IOCSeverity,
  type IOCType,
  type ThreatIOC,
} from '../../../lib/api/threatIntel';

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
const TYPE_FILTERS: Array<{ label: string; value: IOCType | 'all' }> = [
  { label: 'TẤT CẢ', value: 'all' },
  { label: 'IP', value: 'ip' },
  { label: 'DOMAIN', value: 'domain' },
  { label: 'SHA256', value: 'sha256' },
  { label: 'URL', value: 'url' },
];

export const IOCListView: React.FC = () => {
  const [items, setItems] = useState<ThreatIOC[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState<IOCType | 'all'>('all');
  const [severityFilter, setSeverityFilter] = useState<IOCSeverity | 'all'>('all');
  const [watchlistOnly, setWatchlistOnly] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [isCreating, setIsCreating] = useState(false);
  const [form, setForm] = useState({
    type: 'domain' as IOCType,
    value: '',
    severity: 'medium' as IOCSeverity,
    source: '',
    description: '',
  });

  const load = useCallback(() => {
    setIsLoading(true);
    setError('');
    listThreatIOCs({
      pageSize: 50,
      search: search.trim() || undefined,
      type: typeFilter === 'all' ? undefined : typeFilter,
      severity: severityFilter === 'all' ? undefined : severityFilter,
      watchlist: watchlistOnly ? true : undefined,
    })
      .then((page) => {
        setItems(page.items);
        setTotal(page.total);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải danh sách IOC.'))
      .finally(() => setIsLoading(false));
  }, [search, severityFilter, typeFilter, watchlistOnly]);

  useEffect(load, [load]);

  const handleCreate = async (event: React.FormEvent) => {
    event.preventDefault();
    setIsCreating(true);
    setError('');
    const now = new Date().toISOString();
    try {
      await createThreatIOC({
        type: form.type,
        value: form.value,
        severity: form.severity,
        confidence: 'medium',
        source: form.source,
        description: form.description,
        first_seen: now,
        last_seen: now,
        risk_timeline: [{ time: 'now', score: form.severity === 'critical' ? 95 : form.severity === 'high' ? 75 : 45 }],
      });
      setForm({ ...form, value: '', source: '', description: '' });
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể tạo IOC.');
    } finally {
      setIsCreating(false);
    }
  };

  return (
    <IOCLayout>
      <form onSubmit={handleCreate} className="mb-6 grid grid-cols-1 lg:grid-cols-6 gap-2 rounded-lg border border-surface-container-highest bg-background/30 p-3">
        <select value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value as IOCType })} className="bg-background border border-surface-container-highest rounded px-2 py-2 text-xs">
          <option value="ip">IP</option>
          <option value="domain">Domain</option>
          <option value="url">URL</option>
          <option value="sha256">SHA256</option>
        </select>
        <input required value={form.value} onChange={(e) => setForm({ ...form, value: e.target.value })} placeholder="Giá trị IOC" className="lg:col-span-2 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <select value={form.severity} onChange={(e) => setForm({ ...form, severity: e.target.value as IOCSeverity })} className="bg-background border border-surface-container-highest rounded px-2 py-2 text-xs">
          <option value="low">Thấp</option>
          <option value="medium">Trung bình</option>
          <option value="high">Cao</option>
          <option value="critical">Nghiêm trọng</option>
        </select>
        <input required value={form.source} onChange={(e) => setForm({ ...form, source: e.target.value })} placeholder="Nguồn" className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
        <button disabled={isCreating} className="bg-primary text-background rounded px-3 py-2 text-xs font-bold disabled:opacity-50">{isCreating ? 'Đang thêm...' : 'Thêm IOC'}</button>
        <input value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="Mô tả" className="lg:col-span-6 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
      </form>

      <div className="flex flex-wrap gap-3 mb-6">
        <div className="relative flex-1 min-w-[220px]">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
          <input
            aria-label="Tìm kiếm IOC"
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && load()}
            placeholder="Tìm theo giá trị hoặc mô tả"
            className="w-full pl-9 pr-3 py-2 bg-background border border-surface-container-highest rounded-lg text-xs"
          />
        </div>
        <button onClick={load} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-surface-container-highest text-xs"><RefreshCw className="h-3.5 w-3.5" /> Tìm kiếm</button>
        <div className="flex gap-1 items-center">
          {TYPE_FILTERS.map((f) => (
            <button key={f.value} onClick={() => setTypeFilter(f.value)} className={`px-2.5 py-1.5 rounded text-[10px] font-mono font-bold border ${typeFilter === f.value ? 'bg-primary/10 text-primary border-primary/20' : 'border-surface-container-highest text-text-muted'}`}>{f.label}</button>
          ))}
        </div>
        <select value={severityFilter} onChange={(e) => setSeverityFilter(e.target.value as IOCSeverity | 'all')} className="bg-background border border-surface-container-highest rounded-lg px-2 py-1.5 text-[10px]">
          <option value="all">TẤT CẢ MỨC ĐỘ</option>
          <option value="critical">NGHIÊM TRỌNG</option>
          <option value="high">CAO</option>
          <option value="medium">TRUNG BÌNH</option>
          <option value="low">THẤP</option>
        </select>
        <button onClick={() => setWatchlistOnly(!watchlistOnly)} className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[10px] font-mono font-bold ${watchlistOnly ? 'bg-primary/10 text-primary border-primary/20' : 'border-surface-container-highest text-text-muted'}`}>
          {watchlistOnly ? <Eye className="h-3.5 w-3.5" /> : <EyeOff className="h-3.5 w-3.5" />} DANH SÁCH THEO DÕI
        </button>
      </div>

      {error && <div className="mb-4 flex items-center gap-2 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical"><AlertTriangle className="h-4 w-4" />{error}</div>}
      <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest mb-3">{isLoading ? 'Đang tải IOC' : `${total} IOC phù hợp`}</div>

      <div className="overflow-x-auto">
        <table className="w-full text-xs font-mono border-collapse">
          <thead>
            <tr className="border-b border-surface-container-highest">
              <th className="text-left py-2 px-3 text-[9px] text-text-muted font-bold uppercase tracking-widest">Loại</th>
              <th className="text-left py-2 px-3 text-[9px] text-text-muted font-bold uppercase tracking-widest">IOC</th>
              <th className="text-left py-2 px-3 text-[9px] text-text-muted font-bold uppercase tracking-widest">Mức độ</th>
              <th className="text-left py-2 px-3 text-[9px] text-text-muted font-bold uppercase tracking-widest hidden md:table-cell">Lần cuối phát hiện</th>
              <th className="text-center py-2 px-3 text-[9px] text-text-muted font-bold uppercase tracking-widest">Theo dõi</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5} className="text-center py-12 text-text-muted">Đang tải danh sách IOC...</td></tr>
            ) : items.length === 0 ? (
              <tr><td colSpan={5} className="text-center py-12 text-text-muted">Không có IOC nào khớp với bộ lọc hiện tại.</td></tr>
            ) : items.map((ioc) => (
              <tr key={ioc.id} className="border-b border-surface-container-highest/40 hover:bg-surface-container-high/30 group">
                <td className="py-3 px-3"><IOCBadge type={ioc.type} /></td>
                <td className="py-3 px-3 max-w-[220px]">
                  <Link to={`/threat-intelligence/iocs/${ioc.id}`} className="text-text-primary font-bold group-hover:text-primary truncate block" title={ioc.value}>{ioc.value}</Link>
                  <p className="text-[10px] text-text-muted truncate mt-0.5">{ioc.description || ioc.source}</p>
                </td>
                <td className="py-3 px-3"><span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${SEVERITY_CHIP[ioc.severity] ?? ''}`}>{SEVERITY_LABEL[ioc.severity] ?? ioc.severity.toUpperCase()}</span></td>
                <td className="py-3 px-3 text-text-muted hidden md:table-cell">{new Date(ioc.last_seen).toLocaleString()}</td>
                <td className="py-3 px-3 text-center">{ioc.watchlist ? <Eye className="h-3.5 w-3.5 text-primary inline-block" /> : <EyeOff className="h-3.5 w-3.5 text-text-muted inline-block" />}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </IOCLayout>
  );
};

export default IOCListView;
