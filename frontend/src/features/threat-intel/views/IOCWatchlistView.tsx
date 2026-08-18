import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { Eye, RefreshCw } from 'lucide-react';
import { IOCBadge } from '../components/IOCBadge';
import { IOCLayout } from '../components/IOCLayout';
import { listThreatIOCs, type ThreatIOC } from '../../../lib/api/threatIntel';

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

export const IOCWatchlistView: React.FC = () => {
  const [items, setItems] = useState<ThreatIOC[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');

  const load = () => {
    setIsLoading(true);
    setError('');
    listThreatIOCs({ watchlist: true, pageSize: 100 })
      .then((page) => setItems(page.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải danh sách theo dõi.'))
      .finally(() => setIsLoading(false));
  };

  useEffect(load, []);

  return (
    <IOCLayout>
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <Eye className="h-4 w-4 text-primary" />
          <h3 className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">Danh sách theo dõi đang hoạt động</h3>
        </div>
        <button onClick={load} className="flex items-center gap-1 text-xs text-primary"><RefreshCw className="h-3.5 w-3.5" />Làm mới</button>
      </div>
      {error && <div className="mb-4 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical">{error}</div>}
      {isLoading ? (
        <p className="text-text-muted text-xs py-10 text-center">Đang tải danh sách theo dõi...</p>
      ) : items.length === 0 ? (
        <p className="text-text-muted text-xs py-10 text-center border border-dashed border-surface-container-highest rounded-lg">Không có chỉ số nào trong danh sách theo dõi.</p>
      ) : (
        <div className="space-y-2">
          {items.map((ioc) => (
            <Link key={ioc.id} to={`/threat-intelligence/iocs/${ioc.id}`} className="flex items-center gap-3 p-3.5 bg-background/25 border border-surface-container-highest/60 rounded-lg hover:bg-surface-container-high/40 group">
              <IOCBadge type={ioc.type} />
              <div className="flex-1 min-w-0">
                <p className="font-mono text-xs text-text-primary font-bold truncate group-hover:text-primary">{ioc.value}</p>
                <p className="text-[10px] text-text-muted truncate">{ioc.description || ioc.source}</p>
              </div>
              <span className={`px-1.5 py-0.5 rounded text-[9px] font-bold border shrink-0 ${SEVERITY_CHIP[ioc.severity] ?? ''}`}>{SEVERITY_LABEL[ioc.severity] ?? ioc.severity.toUpperCase()}</span>
            </Link>
          ))}
        </div>
      )}
    </IOCLayout>
  );
};

export default IOCWatchlistView;
