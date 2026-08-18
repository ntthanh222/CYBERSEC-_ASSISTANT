import React, { useState } from 'react';
import { ToolkitLayout } from '../../shared/ToolkitLayout';
import { scanUrl } from '../../../../lib/api/tools';
import type { UrlScanResponse } from '../../../../lib/api/tools';
import { ApiError } from '../../../../lib/api/client';
import { Globe, RefreshCw, AlertTriangle, ShieldCheck, ShieldAlert, CheckCircle } from 'lucide-react';

const SEVERITY_STYLES: Record<string, string> = {
  low: 'text-success bg-success/10 border-success/30',
  medium: 'text-warning bg-warning/10 border-warning/30',
  high: 'text-critical bg-critical/10 border-critical/30',
  critical: 'text-critical bg-critical/10 border-critical/30',
};

const SEVERITY_LABEL: Record<string, string> = {
  low: 'Thấp',
  medium: 'Trung bình',
  high: 'Cao',
  critical: 'Nghiêm trọng',
};

const STATUS_LABEL: Record<string, string> = {
  safe: 'An toàn',
  suspicious: 'Đáng ngờ',
  critical: 'Nghiêm trọng',
  failed: 'Thất bại',
  blocked: 'Đã chặn',
};

const ScanResultCard: React.FC<{ result: UrlScanResponse }> = ({ result }) => {
  const isSafe = result.status === 'safe';
  return (
    <div className="space-y-6 animate-fade-in">
      <div className="flex items-center justify-between gap-4 bg-surface-container border border-surface-container-highest rounded-lg p-4">
        <div className="flex items-center gap-3">
          {isSafe ? (
            <CheckCircle className="h-8 w-8 text-success" />
          ) : (
            <ShieldAlert className="h-8 w-8 text-critical" />
          )}
          <div>
            <p className="text-sm font-headline font-bold text-text-primary">{result.normalized_url}</p>
            <p className="text-[10px] font-mono text-text-muted uppercase">
              Trạng thái: {STATUS_LABEL[result.status] ?? result.status} · Điểm rủi ro {result.risk_score}/100
            </p>
          </div>
        </div>
        <span className={`px-2 py-1 rounded border text-[10px] font-mono uppercase font-bold ${SEVERITY_STYLES[result.severity] ?? ''}`}>
          {SEVERITY_LABEL[result.severity] ?? result.severity}
        </span>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs font-mono">
        <div className="bg-surface-container-low rounded-lg p-3 space-y-1">
          <span className="text-text-muted text-[9px] uppercase block">HTTPS</span>
          <span className="text-text-primary font-bold">{result.has_https ? 'Có' : 'Không'}</span>
        </div>
        <div className="bg-surface-container-low rounded-lg p-3 space-y-1">
          <span className="text-text-muted text-[9px] uppercase block">Có thể truy cập</span>
          <span className="text-text-primary font-bold">{result.reachable ? 'Có' : 'Không'}</span>
        </div>
        <div className="bg-surface-container-low rounded-lg p-3 space-y-1">
          <span className="text-text-muted text-[9px] uppercase block">Trạng thái HTTP</span>
          <span className="text-text-primary font-bold">{result.http_status ?? '—'}</span>
        </div>
        <div className="bg-surface-container-low rounded-lg p-3 space-y-1">
          <span className="text-text-muted text-[9px] uppercase block">Chuyển hướng</span>
          <span className="text-text-primary font-bold">{result.redirect_count}</span>
        </div>
      </div>

      {result.failure_reason && (
        <div className="bg-critical/10 border border-critical/30 text-critical text-xs p-3 rounded-lg">
          {result.failure_reason}
        </div>
      )}

      {/* VirusTotal reputation - deliberately its own section, never merged
          into the local findings/risk score above. A clean local scan does
          not mean VirusTotal was even checked, let alone that it agrees. */}
      <div className="space-y-2">
        <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">
          Uy tín VirusTotal
        </span>
        {result.reputation.status === 'not_configured' && (
          <div className="bg-surface-container-low border border-surface-container-highest/60 rounded-lg p-3 text-xs text-text-muted">
            Chưa kiểm tra - VirusTotal chưa được cấu hình trên máy chủ này. Điều này không đồng nghĩa với
            "đã xác nhận an toàn".
          </div>
        )}
        {result.reputation.status === 'unavailable' && (
          <div className="bg-warning/10 border border-warning/30 rounded-lg p-3 text-xs text-warning">
            Không thể kết nối đến VirusTotal ({result.reputation.error_category}). Điều này không đồng nghĩa với
            "đã xác nhận an toàn".
          </div>
        )}
        {result.reputation.status === 'pending' && (
          <div className="bg-surface-container-low border border-surface-container-highest/60 rounded-lg p-3 text-xs text-text-muted">
            VirusTotal vẫn đang phân tích URL này - vui lòng kiểm tra lại sau.
          </div>
        )}
        {result.reputation.status === 'completed' && (
          <div
            className={`rounded-lg p-3 text-xs flex items-center justify-between gap-3 border ${
              result.reputation.malicious > 0
                ? 'bg-critical/10 border-critical/30 text-critical'
                : result.reputation.suspicious > 0
                  ? 'bg-warning/10 border-warning/30 text-warning'
                  : 'bg-success/10 border-success/30 text-success'
            }`}
          >
            <span>
              {result.reputation.malicious} độc hại · {result.reputation.suspicious} nghi ngờ ·{' '}
              {result.reputation.harmless} vô hại · {result.reputation.undetected} chưa phát hiện
            </span>
            {result.reputation.permalink && (
              <a
                href={result.reputation.permalink}
                target="_blank"
                rel="noreferrer noopener"
                className="underline shrink-0"
              >
                Xem trên VirusTotal
              </a>
            )}
          </div>
        )}
      </div>

      {result.findings.length > 0 && (
        <div className="space-y-2">
          <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Phát hiện</span>
          <div className="space-y-1.5">
            {result.findings.map((finding) => (
              <div key={finding.code} className="flex items-start gap-2 bg-surface-container-low rounded-lg p-3 text-xs">
                <AlertTriangle className={`h-4 w-4 mt-0.5 shrink-0 ${SEVERITY_STYLES[finding.severity]?.split(' ')[0] ?? ''}`} />
                <span className="text-text-secondary">{finding.message}</span>
              </div>
            ))}
          </div>
        </div>
      )}

      {result.recommendations.length > 0 && (
        <div className="space-y-2">
          <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Khuyến nghị</span>
          <ul className="space-y-1.5 text-[11px] text-text-secondary">
            {result.recommendations.map((rec, idx) => (
              <li key={idx} className="flex items-start gap-1.5">
                <span className="text-primary mt-0.5">•</span>
                <span>{rec}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
};

export const URLScannerView: React.FC = () => {
  const [urlInput, setUrlInput] = useState('');
  const [isScanning, setIsScanning] = useState(false);
  const [scanResult, setScanResult] = useState<UrlScanResponse | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const handleScan = async (urlToScan: string) => {
    const trimmed = urlToScan.trim();
    if (!trimmed) return;

    setErrorMsg(null);
    setScanResult(null);
    setIsScanning(true);

    try {
      const result = await scanUrl(trimmed);
      setScanResult(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 400) {
        setErrorMsg(err.message);
      } else if (err instanceof ApiError) {
        setErrorMsg(err.message);
      } else {
        setErrorMsg('Không thể kết nối đến URL Scanner.');
      }
    } finally {
      setIsScanning(false);
    }
  };

  const handleRecentClick = (url: string) => {
    setUrlInput(url);
    handleScan(url);
  };

  const handleClear = () => {
    setUrlInput('');
    setScanResult(null);
    setErrorMsg(null);
  };

  const triggerPaste = async () => {
    try {
      const text = await navigator.clipboard.readText();
      setUrlInput(text);
    } catch {
      alert('Không có quyền truy cập clipboard. Vui lòng dán thủ công.');
    }
  };

  const renderContent = () => {
    if (isScanning) {
      return (
        <div className="flex flex-col items-center justify-center py-12 space-y-4 text-center animate-pulse">
          <RefreshCw className="h-10 w-10 text-primary animate-spin" />
          <div className="space-y-1">
            <span className="text-xs font-mono font-bold text-text-primary uppercase tracking-wider block">Đang quét URL...</span>
            <span className="text-[10px] font-mono text-text-muted">Đang phân giải DNS, kiểm tra header chuyển hướng, kiểm tra nguy cơ SSRF</span>
          </div>
        </div>
      );
    }

    if (scanResult) {
      return (
        <div className="space-y-6">
          <div className="flex justify-between items-center border-b border-surface-container-highest/40 pb-4">
            <h3 className="font-headline font-bold text-sm text-text-primary uppercase tracking-wider">Kết quả phân tích</h3>
            <button
              onClick={handleClear}
              className="text-xs text-text-muted hover:text-text-primary font-mono uppercase tracking-wider"
            >
              Xóa kết quả
            </button>
          </div>
          <ScanResultCard result={scanResult} />
        </div>
      );
    }

    return (
      <div className="space-y-6 max-w-2xl mx-auto py-4">

        <div className="space-y-4">

          <div className="space-y-1.5">
            <label className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold" htmlFor="url-input">
              URL đích cần kiểm tra
            </label>
            <div className="relative flex items-center bg-background border border-surface-container-highest focus-within:ring-1 focus-within:ring-primary/40 focus-within:border-primary/40 rounded-lg p-1.5 transition-all">
              <Globe className="h-4 w-4 text-text-muted absolute left-3.5 pointer-events-none" />
              <input
                id="url-input"
                type="text"
                value={urlInput}
                onChange={(e) => { setUrlInput(e.target.value); setErrorMsg(null); }}
                placeholder="https://malicious-domain.attacker.com/login"
                className="w-full bg-transparent border-none py-1.5 pl-10 pr-20 text-xs text-text-primary placeholder:text-text-muted focus:outline-none"
              />
              <div className="absolute right-2 flex items-center gap-1.5">
                <button
                  type="button"
                  onClick={triggerPaste}
                  className="px-2 py-1 hover:bg-surface-container-high rounded text-[9px] font-mono text-text-secondary"
                >
                  DÁN
                </button>
                <button
                  onClick={() => handleScan(urlInput)}
                  className="px-3 py-1.5 bg-primary text-background hover:bg-primary-container rounded-lg text-[10px] font-mono font-bold transition-all active:scale-95"
                >
                  QUÉT
                </button>
              </div>
            </div>
          </div>

          {errorMsg && (
            <div className="bg-critical/10 border border-critical/30 text-critical text-xs p-3 rounded-lg flex items-start gap-2">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{errorMsg}</span>
            </div>
          )}

          <div className="bg-surface-container-low border border-surface-container-highest/60 rounded-lg p-3 flex items-start gap-2.5 text-[10px] text-text-muted font-mono leading-relaxed">
            <ShieldCheck className="h-4 w-4 text-primary mt-0.5 shrink-0" />
            <div>
              <p className="font-bold text-text-secondary uppercase mb-0.5">Bảo vệ SSRF</p>
              <p>
                Các địa chỉ private, loopback, link-local và cloud metadata đều bị chặn trước khi
                thực hiện yêu cầu. Mọi lượt quét đều được ghi vào lịch sử quét.
              </p>
            </div>
          </div>

        </div>

        <div className="pt-6 border-t border-surface-container-highest/40 space-y-3 font-mono">
          <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Thử ví dụ</span>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[10px]">
            <button
              onClick={() => handleRecentClick('https://example.com')}
              className="bg-surface-container-high hover:bg-surface-container-highest border border-surface-container-highest p-3 rounded-lg text-left space-y-1 transition-colors"
            >
              <span className="text-success font-bold block">Tên miền công khai</span>
              <span className="text-text-muted truncate block">https://example.com</span>
            </button>
            <button
              onClick={() => handleRecentClick('http://169.254.169.254')}
              className="bg-surface-container-high hover:bg-surface-container-highest border border-surface-container-highest p-3 rounded-lg text-left space-y-1 transition-colors"
            >
              <span className="text-critical font-bold block">Cloud metadata (đã chặn SSRF)</span>
              <span className="text-text-muted truncate block">http://169.254.169.254</span>
            </button>
          </div>
        </div>

      </div>
    );
  };

  return (
    <ToolkitLayout title="Kiểm tra Website" subtitle="Phân tích cấu hình và mức độ an toàn của website.">
      {renderContent()}
    </ToolkitLayout>
  );
};
export default URLScannerView;
