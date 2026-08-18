import React, { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Area, AreaChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { AlertTriangle, ArrowLeft, Eye, EyeOff, RefreshCw } from 'lucide-react';
import { IOCBadge } from '../components/IOCBadge';
import { IOCLayout } from '../components/IOCLayout';
import { getThreatIOC, setThreatIOCWatchlist, type ThreatIOC } from '../../../lib/api/threatIntel';

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

export const IOCDetailView: React.FC = () => {
  const { id } = useParams<{ id: string }>();
  const [ioc, setIoc] = useState<ThreatIOC | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);

  const load = () => {
    if (!id) return;
    setIsLoading(true);
    setError('');
    getThreatIOC(id)
      .then(setIoc)
      .catch((err) => setError(err instanceof Error ? err.message : 'Không tìm thấy IOC.'))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, [id]);

  const toggleWatchlist = async () => {
    if (!ioc) return;
    setIsSaving(true);
    setError('');
    try {
      setIoc(await setThreatIOCWatchlist(ioc.id, !ioc.watchlist));
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể cập nhật danh sách theo dõi.');
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return <IOCLayout><div className="py-20 text-center text-xs font-mono text-text-muted">Đang tải IOC...</div></IOCLayout>;
  }

  if (!ioc) {
    return (
      <IOCLayout>
        <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted">
          <AlertTriangle className="h-10 w-10 opacity-40" />
          <p className="font-mono text-xs">{error || 'Không tìm thấy IOC.'}</p>
          <button onClick={load} className="flex items-center gap-1 text-primary text-xs"><RefreshCw className="h-3.5 w-3.5" />Thử lại</button>
          <Link to="/threat-intelligence/iocs" className="text-primary text-xs hover:underline">Quay lại danh sách IOC</Link>
        </div>
      </IOCLayout>
    );
  }

  return (
    <IOCLayout>
      <Link to="/threat-intelligence/iocs" className="flex items-center gap-1.5 text-text-muted hover:text-primary text-xs font-mono mb-5">
        <ArrowLeft className="h-3.5 w-3.5" /> Quay lại danh sách IOC
      </Link>
      {error && <div className="mb-4 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical">{error}</div>}

      <div className="flex flex-wrap items-start justify-between gap-4 border-b border-surface-container-highest pb-5 mb-6">
        <div className="space-y-2">
          <div className="flex items-center gap-3 flex-wrap">
            <IOCBadge type={ioc.type} />
            <span className={`px-2 py-0.5 rounded text-[9px] font-bold border ${SEVERITY_CHIP[ioc.severity] ?? ''}`}>{SEVERITY_LABEL[ioc.severity] ?? ioc.severity.toUpperCase()}</span>
            <span className="px-2 py-0.5 rounded text-[9px] font-bold border border-surface-container-highest text-text-muted">{ioc.confidence.toUpperCase()} CONFIDENCE</span>
          </div>
          <p className="font-headline font-black text-xl text-text-primary font-mono break-all">{ioc.value}</p>
          <p className="text-xs text-text-secondary max-w-xl">{ioc.description || 'Chưa có mô tả từ chuyên viên phân tích.'}</p>
        </div>
        <button onClick={toggleWatchlist} disabled={isSaving} className={`flex items-center gap-1.5 px-3 py-2 rounded-lg border text-xs font-mono font-bold ${ioc.watchlist ? 'bg-primary/10 text-primary border-primary/20' : 'border-surface-container-highest text-text-secondary hover:text-primary'} disabled:opacity-50`}>
          {ioc.watchlist ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
          {isSaving ? 'ĐANG LƯU' : ioc.watchlist ? 'ĐANG THEO DÕI' : 'THÊM VÀO DANH SÁCH THEO DÕI'}
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div className="space-y-3">
          <h3 className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">Dòng thời gian điểm rủi ro</h3>
          <div className="bg-background/40 border border-surface-container-highest rounded-lg p-4 h-48">
            {ioc.risk_timeline.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={ioc.risk_timeline} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
                  <XAxis dataKey="time" tick={{ fontSize: 9, fill: '#6b7280' }} />
                  <YAxis domain={[0, 100]} tick={{ fontSize: 9, fill: '#6b7280' }} />
                  <Tooltip contentStyle={{ background: '#1e293b', border: '1px solid #334155', fontSize: 10 }} />
                  <Area type="monotone" dataKey="score" stroke="#ef4444" strokeWidth={2} fill="#ef444433" />
                </AreaChart>
              </ResponsiveContainer>
            ) : <p className="text-xs text-text-muted">Chưa có dữ liệu dòng thời gian rủi ro.</p>}
          </div>
        </div>
        <div className="space-y-3">
          <h3 className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">Ánh xạ MITRE ATT&CK</h3>
          <div className="bg-background/40 border border-surface-container-highest rounded-lg p-4 min-h-[192px] flex flex-col gap-2">
            {ioc.mitre_techniques.length === 0 ? <p className="text-text-muted text-xs">Chưa có kỹ thuật nào được ánh xạ.</p> : ioc.mitre_techniques.map((t) => <span key={t} className="bg-primary/5 border border-primary/15 text-primary px-3 py-1.5 rounded text-[10px] font-mono font-bold">{t}</span>)}
          </div>
        </div>
      </div>

      <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { label: 'Lần đầu phát hiện', value: new Date(ioc.first_seen).toLocaleString() },
          { label: 'Lần cuối phát hiện', value: new Date(ioc.last_seen).toLocaleString() },
          { label: 'Nguồn', value: ioc.source },
          { label: 'Danh sách theo dõi', value: ioc.watchlist ? 'CÓ' : 'KHÔNG' },
        ].map((m) => (
          <div key={m.label} className="bg-background/40 border border-surface-container-highest rounded-lg p-3 space-y-1">
            <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest font-bold block">{m.label}</span>
            <span className="text-xs font-mono text-text-primary font-bold break-words">{m.value}</span>
          </div>
        ))}
      </div>
    </IOCLayout>
  );
};

export default IOCDetailView;
