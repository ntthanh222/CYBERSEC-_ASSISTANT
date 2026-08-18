import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { IOCLayout } from '../components/IOCLayout';
import { listThreatIOCs, type ThreatIOC } from '../../../lib/api/threatIntel';

const NODE_COLOR: Record<string, string> = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#eab308',
  low: '#22c55e',
};

export const IOCGraphView: React.FC = () => {
  const [items, setItems] = useState<ThreatIOC[]>([]);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    listThreatIOCs({ pageSize: 40 })
      .then((page) => setItems(page.items))
      .catch((err) => setError(err instanceof Error ? err.message : 'Không thể tải biểu đồ.'))
      .finally(() => setIsLoading(false));
  }, []);

  const nodes = items.slice(0, 16).map((ioc, index) => {
    const angle = (index / Math.max(items.length, 1)) * Math.PI * 2;
    return {
      ioc,
      x: 310 + Math.cos(angle) * 190,
      y: 230 + Math.sin(angle) * 145,
    };
  });

  return (
    <IOCLayout>
      <div className="space-y-4">
        <div className="flex items-center justify-between flex-wrap gap-2">
          <h3 className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">Biểu đồ Quan hệ IOC</h3>
          <div className="text-[9px] font-mono text-text-muted">{nodes.length} nút</div>
        </div>
        {error && <div className="rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical">{error}</div>}
        <div className="bg-background/40 border border-surface-container-highest rounded-lg overflow-hidden" data-testid="ioc-graph-canvas">
          {isLoading ? (
            <div className="py-24 text-center text-xs text-text-muted">Đang tải biểu đồ...</div>
          ) : nodes.length === 0 ? (
            <div className="py-24 text-center text-xs text-text-muted">Không có chỉ số nào để vẽ biểu đồ.</div>
          ) : (
            <svg width="100%" viewBox="0 0 620 460" aria-label="Biểu đồ Quan hệ IOC">
              <circle cx="310" cy="230" r="42" fill="#0f172a" stroke="#14b8a6" strokeWidth="1.5" />
              <text x="310" y="234" textAnchor="middle" fontSize="10" fill="#14b8a6" fontFamily="monospace" fontWeight="bold">TRUY VẤN</text>
              {nodes.map(({ ioc, x, y }) => (
                <g key={`edge-${ioc.id}`}>
                  <line x1="310" y1="230" x2={x} y2={y} stroke="#475569" strokeWidth="1" strokeDasharray="4 2" />
                </g>
              ))}
              {nodes.map(({ ioc, x, y }) => {
                const color = NODE_COLOR[ioc.severity] ?? '#64748b';
                return (
                  <Link key={ioc.id} to={`/threat-intelligence/iocs/${ioc.id}`}>
                    <g style={{ cursor: 'pointer' }} data-testid={`graph-node-${ioc.id}`}>
                      <circle cx={x} cy={y} r="20" fill={color} fillOpacity="0.16" stroke={color} strokeWidth="1.5" />
                      <text x={x} y={y + 4} textAnchor="middle" fontSize="8" fill={color} fontFamily="monospace" fontWeight="bold">{ioc.type.toUpperCase()}</text>
                      <text x={x} y={y + 34} textAnchor="middle" fontSize="8" fill="#94a3b8" fontFamily="monospace">{ioc.value.substring(0, 16)}</text>
                    </g>
                  </Link>
                );
              })}
            </svg>
          )}
        </div>
      </div>
    </IOCLayout>
  );
};

export default IOCGraphView;
