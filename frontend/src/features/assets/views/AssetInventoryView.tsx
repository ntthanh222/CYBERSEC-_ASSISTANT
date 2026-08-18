import React, { useState, useEffect, useCallback } from 'react';
import { AssetDrawer } from '../components/AssetDrawer';
import { AssetCreateForm } from '../components/AssetCreateForm';
import { listAssets } from '../../../lib/api/assets';
import type { AssetRecord, AssetType, BusinessCriticality } from '../../../lib/api/assets';
import { ApiError } from '../../../lib/api/client';
import { Server, Database, Monitor, Network, Cloud, Globe, ShieldAlert, AlertTriangle, CheckCircle, RefreshCw, Plus } from 'lucide-react';

const TYPE_ICON: Record<AssetType, React.ElementType> = {
  server: Server,
  database: Database,
  workstation: Monitor,
  network_device: Network,
  cloud_resource: Cloud,
};

const CRIT_CHIP: Record<BusinessCriticality, string> = {
  critical: 'bg-critical/10 text-critical border-critical/20',
  high: 'bg-high/10 text-high border-high/20',
  medium: 'bg-warning/10 text-warning border-warning/20',
  low: 'bg-success/10 text-success border-success/20',
};

const PATCH_CHIP: Record<string, string> = {
  patched: 'text-success',
  in_progress: 'text-warning',
  not_started: 'text-critical',
  accepted_risk: 'text-secondary',
  unknown: 'text-text-muted',
  not_applicable: 'text-text-muted',
};

const CRIT_LABEL: Record<string, string> = {
  critical: 'Nghiêm trọng',
  high: 'Cao',
  medium: 'Trung bình',
  low: 'Thấp',
};

const PATCH_LABEL: Record<string, string> = {
  patched: 'Đã vá',
  in_progress: 'Đang xử lý',
  not_started: 'Chưa bắt đầu',
  accepted_risk: 'Chấp nhận rủi ro',
  unknown: 'Chưa rõ',
  not_applicable: 'Không áp dụng',
};

const TYPE_LABEL: Record<string, string> = {
  server: 'MÁY CHỦ',
  workstation: 'MÁY TRẠM',
  cloud_resource: 'TÀI NGUYÊN CLOUD',
  database: 'CƠ SỞ DỮ LIỆU',
  network_device: 'THIẾT BỊ MẠNG',
};

const TYPE_FILTERS: Array<{ label: string; value: AssetType | 'all' }> = [
  { label: 'TẤT CẢ', value: 'all' },
  { label: 'MÁY CHỦ', value: 'server' },
  { label: 'CƠ SỞ DỮ LIỆU', value: 'database' },
  { label: 'MÁY TRẠM', value: 'workstation' },
  { label: 'MẠNG', value: 'network_device' },
];

const PAGE_SIZE = 50;

export const AssetInventoryView: React.FC = () => {
  const [assets, setAssets] = useState<AssetRecord[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const [selectedAsset, setSelectedAsset] = useState<AssetRecord | null>(null);
  const [typeFilter, setTypeFilter] = useState<AssetType | 'all'>('all');
  const [critFilter, setCritFilter] = useState<BusinessCriticality | 'all'>('all');
  const [exposedOnly, setExposedOnly] = useState(false);
  const [showCreateForm, setShowCreateForm] = useState(false);

  const fetchAssets = useCallback(() => {
    setIsLoading(true);
    listAssets({
      page: 1,
      pageSize: PAGE_SIZE,
      type: typeFilter === 'all' ? undefined : typeFilter,
      businessCriticality: critFilter === 'all' ? undefined : critFilter,
    })
      .then((res) => {
        setAssets(res.items);
        setErrorMsg(null);
      })
      .catch((err) => {
        setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải danh sách tài sản.');
      })
      .finally(() => setIsLoading(false));
  }, [typeFilter, critFilter]);

  useEffect(() => {
    fetchAssets();
  }, [fetchAssets]);

  const filtered = assets.filter((a) => !exposedOnly || a.internet_exposed);

  const critCount = assets.filter((a) => a.business_criticality === 'critical').length;
  const exposedCount = assets.filter((a) => a.internet_exposed).length;
  const patchedCount = assets.filter((a) => a.patch_status === 'patched').length;

  const renderContent = () => {
    if (isLoading) {
      return (
        <div
          className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl"
          data-testid="asset-inventory-loading"
        >
          <RefreshCw className="h-8 w-8 animate-spin text-primary" />
          <p className="text-xs font-mono uppercase tracking-widest">Đang tải danh sách tài sản...</p>
        </div>
      );
    }

    if (errorMsg) {
      return (
        <div
          className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl"
          data-testid="asset-inventory-error"
        >
          <AlertTriangle className="h-10 w-10 text-critical" />
          <h3 className="font-headline font-bold text-sm text-text-primary">Không thể tải tài sản</h3>
          <p className="text-xs text-text-secondary">{errorMsg}</p>
          <button
            onClick={fetchAssets}
            className="mt-1 px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold border border-surface-container-highest text-text-secondary hover:text-text-primary hover:bg-surface-container-high transition-all"
          >
            THỬ LẠI
          </button>
        </div>
      );
    }

    if (assets.length === 0) {
      return (
        <div
          className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted bg-surface-container border border-surface-container-highest rounded-xl"
          data-testid="asset-inventory-empty"
        >
          <ShieldAlert className="h-10 w-10 opacity-30" />
          <p className="text-xs italic">Chưa có tài sản nào được đăng ký.</p>
          <button
            onClick={() => setShowCreateForm(true)}
            className="mt-1 flex items-center gap-1.5 px-3 py-1.5 bg-primary text-background rounded-lg text-[10px] font-mono font-bold hover:bg-primary-container transition-all"
          >
            <Plus className="h-3.5 w-3.5" />
            THÊM TÀI SẢN ĐẦU TIÊN
          </button>
        </div>
      );
    }

    return (
      <div className="overflow-x-auto">
        <table className="w-full text-xs text-left border-collapse font-mono">
          <thead>
            <tr className="border-b border-surface-container-highest text-[9px] text-text-muted uppercase tracking-widest">
              <th className="py-2.5 px-3">Loại</th>
              <th className="py-2.5 px-3">Tên tài sản</th>
              <th className="py-2.5 px-3">Địa chỉ IP</th>
              <th className="py-2.5 px-3">Mức độ nghiêm trọng</th>
              <th className="py-2.5 px-3">Mức độ lộ diện</th>
              <th className="py-2.5 px-3">Trạng thái vá lỗi</th>
            </tr>
          </thead>
          <tbody>
            {filtered.length === 0 ? (
              <tr>
                <td colSpan={6} className="text-center py-12 text-text-muted italic text-xs">
                  Không có tài sản nào khớp với bộ lọc hiện tại.
                </td>
              </tr>
            ) : (
              filtered.map((a) => {
                const Icon = TYPE_ICON[a.type] || Server;
                return (
                  <tr
                    key={a.id}
                    onClick={() => setSelectedAsset(a)}
                    onKeyDown={(e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        setSelectedAsset(a);
                      }
                    }}
                    tabIndex={0}
                    role="button"
                    className="border-b border-surface-container-highest/45 hover:bg-surface-container-high/30 cursor-pointer transition-all focus:outline-none focus:ring-1 focus:ring-primary/40"
                    data-testid={`asset-row-${a.id}`}
                  >
                    <td className="py-3.5 px-3">
                      <div className="flex items-center gap-1.5" title={a.type.toUpperCase()}>
                        <Icon className="h-4 w-4 text-text-secondary shrink-0" />
                        <span className="text-[9px] text-text-muted hidden md:inline">{TYPE_LABEL[a.type] ?? a.type.toUpperCase()}</span>
                      </div>
                    </td>
                    <td className="py-3.5 px-3 font-body">
                      <span className="font-bold text-text-primary group-hover:text-primary transition-colors block">{a.name}</span>
                      <span className="text-[10px] font-mono text-text-muted">{a.hostname}</span>
                    </td>
                    <td className="py-3.5 px-3 font-mono text-text-secondary">{a.ip_address}</td>
                    <td className="py-3.5 px-3">
                      <span className={`px-2 py-0.5 rounded text-[9px] font-bold border capitalize ${CRIT_CHIP[a.business_criticality] ?? ''}`}>
                        {CRIT_LABEL[a.business_criticality] ?? a.business_criticality}
                      </span>
                    </td>
                    <td className="py-3.5 px-3">
                      {a.internet_exposed ? (
                        <span className="text-critical font-bold">Lộ diện Internet</span>
                      ) : (
                        <span className="text-text-muted">Nội bộ</span>
                      )}
                    </td>
                    <td className="py-3.5 px-3">
                      <span className={`capitalize font-bold ${PATCH_CHIP[a.patch_status ?? 'unknown'] ?? ''}`}>
                        {PATCH_LABEL[a.patch_status ?? 'unknown'] ?? (a.patch_status ?? 'unknown').replace('_', ' ')}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    );
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Asset Inventory</h2>
          <p className="text-xs text-text-secondary">Danh mục hạ tầng riêng của bạn — được nhập và duy trì bởi bạn.</p>
        </div>
        <button
          onClick={() => setShowCreateForm(true)}
          className="flex items-center gap-1.5 px-3 py-2 bg-primary text-background rounded-lg text-xs font-mono font-bold hover:bg-primary-container transition-all"
          data-testid="add-asset-button"
        >
          <Plus className="h-4 w-4" />
          THÊM TÀI SẢN
        </button>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {[
          { label: 'Tổng số tài sản', value: assets.length, icon: Server, color: 'text-text-primary' },
          { label: 'Nghiêm trọng', value: critCount, icon: AlertTriangle, color: 'text-critical' },
          { label: 'Lộ diện Internet', value: exposedCount, icon: Globe, color: 'text-high' },
          { label: 'Đã vá đầy đủ', value: patchedCount, icon: CheckCircle, color: 'text-success' },
        ].map((s) => {
          const Icon = s.icon;
          return (
            <div key={s.label} className="bg-surface-container border border-surface-container-highest rounded-xl p-4 space-y-1">
              <div className="flex items-center justify-between">
                <span className="text-[9px] font-mono uppercase tracking-widest text-text-muted font-bold">{s.label}</span>
                <Icon className={`h-4 w-4 ${s.color}`} />
              </div>
              <span className={`text-3xl font-headline font-black ${s.color}`}>{s.value}</span>
            </div>
          );
        })}
      </div>

      {/* Filter bar */}
      <div className="flex flex-wrap gap-2 items-center">
        {TYPE_FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setTypeFilter(f.value)}
            className={`px-2.5 py-1.5 rounded text-[10px] font-mono font-bold border transition-all ${
              typeFilter === f.value
                ? 'bg-primary/10 text-primary border-primary/20'
                : 'border-surface-container-highest text-text-muted hover:text-text-primary'
            }`}
          >
            {f.label}
          </button>
        ))}

        <select
          value={critFilter}
          onChange={(e) => setCritFilter(e.target.value as BusinessCriticality | 'all')}
          className="bg-background border border-surface-container-highest rounded-lg px-2.5 py-1.5 text-[10px] font-mono font-bold text-text-primary focus:outline-none"
        >
          <option value="all">TẤT CẢ MỨC ĐỘ</option>
          <option value="critical">NGHIÊM TRỌNG</option>
          <option value="high">CAO</option>
          <option value="medium">TRUNG BÌNH</option>
          <option value="low">THẤP</option>
        </select>

        <button
          onClick={() => setExposedOnly(!exposedOnly)}
          className={`px-2.5 py-1.5 rounded text-[10px] font-mono font-bold border transition-all ${
            exposedOnly
              ? 'bg-primary/10 text-primary border-primary/20'
              : 'border-surface-container-highest text-text-muted hover:text-text-primary'
          }`}
        >
          LỘ DIỆN INTERNET
        </button>
      </div>

      <div className="text-[9px] font-mono text-text-muted uppercase tracking-widest">
        {filtered.length} tài sản khớp điều kiện
      </div>

      {/* Content Area */}
      {renderContent()}

      {/* Detail slideout drawer */}
      {selectedAsset && (
        <AssetDrawer
          asset={selectedAsset}
          onClose={() => setSelectedAsset(null)}
        />
      )}

      {/* Create form modal */}
      {showCreateForm && (
        <AssetCreateForm
          onClose={() => setShowCreateForm(false)}
          onCreated={() => {
            setShowCreateForm(false);
            fetchAssets();
          }}
        />
      )}
    </div>
  );
};

export default AssetInventoryView;
