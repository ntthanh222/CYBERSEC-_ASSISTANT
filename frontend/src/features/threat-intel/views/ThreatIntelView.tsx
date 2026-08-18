import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Eye, RefreshCw, ShieldCheck, Zap } from 'lucide-react';
import { IOCBadge } from '../components/IOCBadge';
import { IOCLayout } from '../components/IOCLayout';
import { getThreatIntelSummary, type ThreatIntelSummary } from '../../../lib/api/threatIntel';

const SEVERITY_CHIP: Record<string, string> = {
  critical: 'bg-critical/10 text-critical border-critical/20',
  high: 'bg-high/10 text-high border-high/20',
  medium: 'bg-warning/10 text-warning border-warning/20',
  low: 'bg-success/10 text-success border-success/20',
};

export const ThreatIntelView: React.FC = () => {
  const [summary, setSummary] = useState<ThreatIntelSummary | null>(null);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const load = () => {
    setIsLoading(true);
    setError('');
    getThreatIntelSummary()
      .then(setSummary)
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải thông tin tình báo mối đe dọa.'))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);

  const stats = [
    { label: 'Tổng số IOC', value: summary?.total ?? 0, icon: AlertTriangle, color: 'text-text-primary' },
    { label: 'Nghiêm trọng', value: summary?.critical ?? 0, icon: Zap, color: 'text-critical' },
    { label: 'Trong danh sách theo dõi', value: summary?.watchlist ?? 0, icon: Eye, color: 'text-primary' },
    { label: 'Gần đây (48h)', value: summary?.recent_48h ?? 0, icon: ShieldCheck, color: 'text-success' },
  ];

  return (
    <IOCLayout>
      {error && (
        <div className="mb-5 flex items-center justify-between gap-3 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical">
          <span>{error}</span>
          <button onClick={load} className="flex items-center gap-1 font-bold text-text-primary">
            <RefreshCw className="h-3.5 w-3.5" /> Thử lại
          </button>
        </div>
      )}

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
        {stats.map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="bg-background/40 border border-surface-container-highest rounded-lg p-4 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">{s.label}</span>
                <Icon className={`h-4 w-4 ${s.color}`} />
              </div>
              <span className={`text-3xl font-headline font-black block ${s.color}`}>
                {isLoading ? '...' : s.value}
              </span>
            </div>
          );
        })}
      </div>

      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">Nguồn Chỉ số Gần đây</h3>
          <Link to="/threat-intelligence/iocs" className="text-[9px] text-primary hover:underline font-mono">XEM TẤT CẢ</Link>
        </div>

        {isLoading ? (
          <div className="py-12 text-center text-xs font-mono text-text-muted">Đang tải chỉ số...</div>
        ) : summary && summary.items.length > 0 ? (
          <div className="space-y-2">
            {summary.items.map((ioc) => (
              <Link
                key={ioc.id}
                to={`/threat-intelligence/iocs/${ioc.id}`}
                className="flex items-center gap-3 p-3 bg-background/25 border border-surface-container-highest/60 rounded-lg hover:bg-surface-container-high/40 transition-all group"
              >
                <IOCBadge type={ioc.type} />
                <div className="flex-1 min-w-0">
                  <p className="font-mono text-xs text-text-primary font-bold truncate group-hover:text-primary transition-colors">{ioc.value}</p>
                  <p className="text-[10px] text-text-muted truncate mt-0.5">{ioc.description || ioc.source}</p>
                </div>
                <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border ${SEVERITY_CHIP[ioc.severity] ?? ''}`}>
                  {ioc.severity.toUpperCase()}
                </span>
              </Link>
            ))}
          </div>
        ) : (
          <div className="py-12 text-center text-xs text-text-muted border border-dashed border-surface-container-highest rounded-lg">
            Chưa có chỉ số nào được thêm.
            <Link to="/threat-intelligence/iocs" className="ml-2 text-primary hover:underline">Thêm IOC đầu tiên</Link>
          </div>
        )}
      </div>
    </IOCLayout>
  );
};

export default ThreatIntelView;
