import React, { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import { getAsset } from '../../../lib/api/assets';
import type { AssetRecord } from '../../../lib/api/assets';
import { getCve } from '../../../lib/api/cves';
import type { CveResult } from '../../../lib/api/cves';
import { ApiError } from '../../../lib/api/client';
import { ArrowLeft, AlertTriangle, ShieldCheck, RefreshCw } from 'lucide-react';

const CVSS_COLOR = (score: number) => {
  if (score >= 9) return 'text-critical';
  if (score >= 7) return 'text-high';
  if (score >= 4) return 'text-warning';
  return 'text-success';
};

const PATCH_CHIP: Record<string, string> = {
  patched: 'bg-success/10 text-success border-success/20',
  in_progress: 'bg-warning/10 text-warning border-warning/20',
  not_started: 'bg-critical/10 text-critical border-critical/20',
  accepted_risk: 'bg-secondary/10 text-secondary border-secondary/20',
  unknown: 'border-surface-container-highest text-text-muted',
  not_applicable: 'border-surface-container-highest text-text-muted',
};

export const AssetProfileView: React.FC = () => {
  const { id } = useParams<{ id: string }>();

  const [asset, setAsset] = useState<AssetRecord | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Best-effort live CVE enrichment. A single failed lookup (e.g. an id the
  // analyst mistyped, or a transient upstream error) never blocks the rest
  // of the page - it just renders that one CVE as "details unavailable".
  const [cveDetails, setCveDetails] = useState<Record<string, CveResult | 'error'>>({});

  const fetchAsset = () => {
    if (!id) return;
    setIsLoading(true);
    setNotFound(false);
    setErrorMsg(null);
    getAsset(id)
      .then((record) => setAsset(record))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) {
          setNotFound(true);
        } else {
          setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải thông tin tài sản này.');
        }
      })
      .finally(() => setIsLoading(false));
  };

  useEffect(fetchAsset, [id]);

  useEffect(() => {
    if (!asset || asset.linked_cves.length === 0) return;
    let cancelled = false;
    asset.linked_cves.forEach((cveId) => {
      getCve(cveId)
        .then((result) => {
          if (!cancelled) setCveDetails((prev) => ({ ...prev, [cveId]: result }));
        })
        .catch(() => {
          if (!cancelled) setCveDetails((prev) => ({ ...prev, [cveId]: 'error' }));
        });
    });
    return () => {
      cancelled = true;
    };
  }, [asset]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted" data-testid="asset-profile-loading">
        <RefreshCw className="h-8 w-8 animate-spin text-primary" />
        <p className="text-xs font-mono uppercase tracking-widest">Đang tải tài sản...</p>
      </div>
    );
  }

  if (notFound || !asset) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted">
        <AlertTriangle className="h-10 w-10 opacity-40" />
        <p className="font-mono text-xs">Không tìm thấy tài sản trong danh mục.</p>
        <Link to="/assets" className="text-primary text-xs hover:underline">← Quay lại danh mục</Link>
      </div>
    );
  }

  if (errorMsg) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted" data-testid="asset-profile-error">
        <AlertTriangle className="h-10 w-10 text-critical" />
        <p className="text-xs text-text-secondary">{errorMsg}</p>
        <button
          onClick={fetchAsset}
          className="mt-1 px-3 py-1.5 rounded-lg text-[10px] font-mono font-bold border border-surface-container-highest text-text-secondary hover:text-text-primary hover:bg-surface-container-high transition-all"
        >
          THỬ LẠI
        </button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="border-b border-surface-container-highest/60 pb-4">
        <Link to="/assets" className="flex items-center gap-1.5 text-text-muted hover:text-primary text-xs font-mono mb-3 transition-colors">
          <ArrowLeft className="h-3.5 w-3.5" />
          Asset Inventory
        </Link>
        <div className="flex items-start justify-between flex-wrap gap-4">
          <div>
            <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">{asset.name}</h2>
            <p className="text-xs text-text-secondary font-mono">{asset.hostname} · {asset.ip_address}</p>
          </div>
          <span className={`px-3 py-1.5 rounded-lg text-xs font-mono font-bold border ${PATCH_CHIP[asset.patch_status ?? 'unknown']}`}>
            PATCH: {(asset.patch_status ?? 'unknown').replace('_', ' ').toUpperCase()}
          </span>
        </div>
      </div>

      {/* Host Parameters */}
      <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5 space-y-4">
        <h3 className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">Thông số máy chủ</h3>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3 font-mono text-xs">
          {[
            { label: 'Hệ điều hành', value: asset.operating_system },
            { label: 'Loại tài sản', value: asset.type.replace('_', ' ').toUpperCase() },
            { label: 'Mức độ nghiêm trọng', value: asset.business_criticality.toUpperCase() },
            { label: 'Chủ sở hữu', value: asset.owner },
            { label: 'Phòng ban', value: asset.department },
            { label: 'Lộ diện Internet', value: asset.internet_exposed ? 'YES' : 'NO' },
            { label: 'Bằng chứng khai thác', value: (asset.exploit_evidence ?? 'none').replace('_', ' ').toUpperCase() },
            { label: 'Cập nhật lần cuối', value: new Date(asset.updated_at).toLocaleDateString() },
            { label: 'Ngày tạo', value: new Date(asset.created_at).toLocaleDateString() },
          ].map((f) => (
            <div key={f.label} className="bg-background/40 border border-surface-container-highest/40 rounded-lg p-3 space-y-1">
              <span className="text-[8px] font-mono text-text-muted uppercase tracking-widest block">{f.label}</span>
              <span className="text-text-primary font-bold">{f.value}</span>
            </div>
          ))}
        </div>
        {asset.description && (
          <p className="text-xs text-text-secondary bg-background/20 border border-surface-container-highest/40 rounded-lg p-3 leading-relaxed">
            {asset.description}
          </p>
        )}
      </div>

      {/* Linked Vulnerabilities — enriched live via GET /api/cves/{id} (NVD, cached) */}
      <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5 space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">
            Linked Vulnerabilities ({asset.linked_cves.length})
          </h3>
        </div>

        {asset.linked_cves.length === 0 ? (
          <div className="flex flex-col items-center py-8 gap-2 text-text-muted">
            <ShieldCheck className="h-8 w-8 opacity-40" />
            <p className="text-xs italic">Không có lỗ hổng nào được liên kết. Tài sản này an toàn.</p>
          </div>
        ) : (
          <div className="space-y-3">
            {asset.linked_cves.map((cveId) => {
              const detail = cveDetails[cveId];
              if (detail === undefined) {
                return (
                  <div key={cveId} className="flex items-center gap-3 p-4 bg-background/40 border border-surface-container-highest/60 rounded-lg" data-testid={`cve-loading-${cveId}`}>
                    <RefreshCw className="h-4 w-4 animate-spin text-text-muted shrink-0" />
                    <span className="font-mono font-bold text-sm text-text-primary">{cveId}</span>
                  </div>
                );
              }
              if (detail === 'error') {
                return (
                  <div key={cveId} className="flex items-center justify-between gap-4 p-4 bg-background/40 border border-surface-container-highest/60 rounded-lg" data-testid={`cve-error-${cveId}`}>
                    <span className="font-mono font-bold text-sm text-text-primary">{cveId}</span>
                    <span className="text-[10px] text-text-muted italic">Không có thông tin chi tiết</span>
                  </div>
                );
              }
              return (
                <div
                  key={cveId}
                  className="flex items-start gap-4 p-4 bg-background/40 border border-surface-container-highest/60 rounded-lg hover:bg-surface-container-high/30 transition-all"
                  data-testid={`cve-detail-${cveId}`}
                >
                  <div className="flex-1 min-w-0 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="font-mono font-black text-sm text-text-primary">{detail.cve_id}</span>
                      {detail.severity && (
                        <span className={`text-[9px] font-mono font-bold px-1.5 py-0.5 rounded border ${
                          detail.severity === 'critical' ? 'bg-critical/10 text-critical border-critical/20' :
                          detail.severity === 'high' ? 'bg-high/10 text-high border-high/20' :
                          'bg-warning/10 text-warning border-warning/20'
                        }`}>
                          {detail.severity.toUpperCase()}
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-text-secondary line-clamp-2">{detail.description}</p>
                  </div>
                  {detail.cvss_score !== null && (
                    <div className="shrink-0 text-right space-y-1">
                      <span className={`text-2xl font-headline font-black ${CVSS_COLOR(detail.cvss_score)}`}>{detail.cvss_score.toFixed(1)}</span>
                      <p className="text-[8px] text-text-muted font-mono uppercase">CVSS</p>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default AssetProfileView;
