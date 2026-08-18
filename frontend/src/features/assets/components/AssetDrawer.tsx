import React from 'react';
import { X, ExternalLink, ShieldAlert } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { AssetRecord } from '../../../lib/api/assets';

interface AssetDrawerProps {
  asset: AssetRecord;
  onClose: () => void;
}

const PATCH_CHIP: Record<string, string> = {
  patched: 'bg-success/10 text-success border-success/20',
  in_progress: 'bg-warning/10 text-warning border-warning/20',
  not_started: 'bg-critical/10 text-critical border-critical/20',
  accepted_risk: 'bg-secondary/10 text-secondary border-secondary/20',
  unknown: 'bg-surface-container-highest text-text-muted border-surface-container-highest',
  not_applicable: 'bg-surface-container-highest text-text-muted border-surface-container-highest',
};

export const AssetDrawer: React.FC<AssetDrawerProps> = ({ asset, onClose }) => {
  const linkedCves = asset.linked_cves ?? [];

  return (
    <>
      {/* Overlay */}
      <div
        className="fixed inset-0 bg-black/50 z-40 transition-opacity"
        onClick={onClose}
        data-testid="drawer-overlay"
      />

      {/* Drawer panel */}
      <div
        className="fixed top-0 right-0 h-full w-full max-w-md bg-background border-l border-surface-container-highest z-50 overflow-y-auto shadow-2xl"
        data-testid="asset-drawer"
      >
        {/* Header */}
        <div className="sticky top-0 bg-background border-b border-surface-container-highest/60 p-5 flex items-start justify-between gap-4">
          <div>
            <p className="text-[9px] font-mono text-text-muted uppercase tracking-widest mb-1">Hồ sơ Tài sản</p>
            <h3 className="font-headline font-black text-lg text-text-primary">{asset.name}</h3>
            <p className="text-xs text-text-secondary font-mono">{asset.hostname}</p>
          </div>
          <button
            onClick={onClose}
            aria-label="Đóng ngăn kéo"
            className="p-1.5 rounded-lg border border-surface-container-highest text-text-muted hover:text-text-primary hover:bg-surface-container-high transition-all"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="p-5 space-y-6">
          {/* Host Parameters */}
          <div className="space-y-3">
            <h4 className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">Thông số Máy chủ</h4>
            <div className="grid grid-cols-2 gap-2 text-xs font-mono">
              {[
                { label: 'IP', value: asset.ip_address },
                { label: 'HĐH', value: asset.operating_system },
                { label: 'Loại', value: asset.type.replace('_', ' ').toUpperCase() },
                { label: 'Chủ sở hữu', value: asset.owner },
                { label: 'Phòng ban', value: asset.department },
                { label: 'Lộ Internet', value: asset.internet_exposed ? 'CÓ' : 'KHÔNG' },
              ].map(f => (
                <div key={f.label} className="bg-background/40 border border-surface-container-highest/40 rounded-lg p-2">
                  <span className="text-[8px] text-text-muted uppercase block">{f.label}</span>
                  <span className="text-text-primary font-bold">{f.value}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Patch Status */}
          <div className="space-y-2">
            <h4 className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">Trạng thái Vá lỗi</h4>
            <span className={`inline-flex px-2.5 py-1 rounded text-[10px] font-bold border ${PATCH_CHIP[asset.patch_status ?? 'unknown']}`}>
              {(asset.patch_status ?? 'unknown').replace('_', ' ').toUpperCase()}
            </span>
          </div>

          {/* Linked CVE IDs — full details (CVSS/severity) fetched live on the
              asset profile page; the drawer stays a light-weight preview. */}
          <div className="space-y-3">
            <h4 className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">
              CVE liên kết ({linkedCves.length})
            </h4>
            {linkedCves.length === 0 ? (
              <p className="text-text-muted text-xs italic">Không có CVE liên kết.</p>
            ) : (
              <div className="flex flex-wrap gap-1.5">
                {linkedCves.map((cveId) => (
                  <span
                    key={cveId}
                    className="text-[10px] font-mono font-bold px-2 py-1 bg-background/40 border border-surface-container-highest/60 rounded-lg text-text-primary"
                  >
                    {cveId}
                  </span>
                ))}
              </div>
            )}
          </div>

          {/* Actions */}
          <div className="flex gap-2 pt-2">
            <Link
              to={`/assets/${asset.id}`}
              className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-primary text-background hover:bg-primary-container rounded-lg text-xs font-mono font-bold transition-all"
            >
              <ExternalLink className="h-3.5 w-3.5" />
              HỒ SƠ ĐẦY ĐỦ
            </Link>
            <Link
              to="/vulnerabilities/patches"
              className="flex items-center justify-center gap-1.5 px-3 py-2 border border-surface-container-highest text-text-secondary hover:text-text-primary rounded-lg text-xs font-mono font-bold transition-all"
            >
              <ShieldAlert className="h-3.5 w-3.5" />
              BẢN VÁ
            </Link>
          </div>
        </div>
      </div>
    </>
  );
};

export default AssetDrawer;
