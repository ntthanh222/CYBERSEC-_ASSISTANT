import React from 'react';
import { useNavigate } from 'react-router-dom';
import { WifiOff, RefreshCw, Database, Server, Sparkles, ArrowLeft, LogIn } from 'lucide-react';
import { useBackendAvailability } from '../../../lib/network/ConnectionRecoveryProvider';

function statusCopy(status: ReturnType<typeof useBackendAvailability>['status']): {
  title: string;
  reason: string;
} {
  switch (status) {
    case 'offline':
      return {
        title: 'Không có kết nối mạng',
        reason: 'Trình duyệt báo không có kết nối mạng nào đang hoạt động.',
      };
    case 'backend_unreachable':
      return {
        title: 'Không thể kết nối máy chủ backend',
        reason: 'Không thể kết nối tới máy chủ ứng dụng. Máy chủ có thể đang khởi động, khởi động lại hoặc đã dừng.',
      };
    case 'degraded':
      return {
        title: 'Hệ thống suy giảm',
        reason: 'Có thể kết nối tới backend, nhưng một thành phần phụ thuộc bắt buộc đang không hoạt động bình thường.',
      };
    case 'checking':
      return {
        title: 'Đang kiểm tra kết nối...',
        reason: 'Đang chạy kiểm tra mới với backend.',
      };
    case 'restored':
      return {
        title: 'Đã khôi phục kết nối',
        reason: 'Đã kết nối lại được với backend. Đang đưa bạn quay lại vị trí trước đó.',
      };
    default:
      return {
        title: 'Khôi phục kết nối',
        reason: 'Đang theo dõi trạng thái kết nối.',
      };
  }
}

function DependencyRow({
  label,
  icon: Icon,
  status,
}: {
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  status: string | null;
}) {
  const isHealthy = status === 'healthy';
  const isUnknown = status === null;
  return (
    <div className="flex items-center justify-between py-2 border-b border-surface-container-highest/40 last:border-0">
      <div className="flex items-center gap-2 text-text-secondary">
        <Icon className="h-3.5 w-3.5" />
        <span className="text-[11px] font-mono">{label}</span>
      </div>
      <span
        className={`text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border ${
          isUnknown
            ? 'text-text-muted border-surface-container-highest'
            : isHealthy
              ? 'text-primary border-primary/30 bg-primary/10'
              : 'text-critical border-critical/30 bg-critical/10'
        }`}
      >
        {isUnknown ? 'UNKNOWN' : status}
      </span>
    </div>
  );
}

export const OfflineView: React.FC = () => {
  const { status, checks, embedding, lastCheckedAt, checkNow } = useBackendAvailability();
  const navigate = useNavigate();
  const { title, reason } = statusCopy(status);
  const isChecking = status === 'checking';

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center px-4 py-12 text-center font-body">
      <div
        className={`h-16 w-16 rounded-full border flex items-center justify-center mb-6 ${
          status === 'restored'
            ? 'bg-primary/10 border-primary/30'
            : 'bg-warning/10 border-warning/30 animate-pulse'
        }`}
      >
        <WifiOff className={`h-8 w-8 ${status === 'restored' ? 'text-primary' : 'text-warning'}`} />
      </div>

      <h1 className="font-headline font-black text-2xl text-text-primary tracking-tight mb-2">{title}</h1>
      <p
        className="text-xs font-mono text-warning uppercase tracking-widest mb-4"
        role="status"
        aria-live="polite"
      >
        {status.replace('_', ' ').toUpperCase()}
      </p>

      <p className="text-xs text-text-secondary max-w-md mb-6 leading-relaxed">{reason}</p>

      {checks && (
        <div className="w-full max-w-sm bg-surface-container border border-surface-container-highest rounded-xl p-4 mb-6 text-left">
          <DependencyRow label="Backend" icon={Server} status={checks.backend.status} />
          <DependencyRow label="Cơ sở dữ liệu" icon={Database} status={checks.database.status} />
          <DependencyRow label="Cache (Redis)" icon={Database} status={checks.redis.status} />
          {embedding && (
            <div className="flex items-center justify-between py-2">
              <div className="flex items-center gap-2 text-text-secondary">
                <Sparkles className="h-3.5 w-3.5" />
                <span className="text-[11px] font-mono">Mô hình AI</span>
              </div>
              <span className="text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border text-text-muted border-surface-container-highest">
                {embedding.status.replace('_', ' ')}
              </span>
            </div>
          )}
        </div>
      )}

      <p className="text-[10px] font-mono text-text-muted mb-6">
        {lastCheckedAt ? `Kiểm tra lần cuối: ${new Date(lastCheckedAt).toLocaleTimeString()}` : 'Chưa kiểm tra.'}
      </p>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          onClick={checkNow}
          disabled={isChecking}
          className="flex items-center gap-2 px-5 py-2.5 bg-primary text-background hover:bg-primary-container rounded-lg text-xs font-bold transition-all disabled:opacity-50"
        >
          <RefreshCw className={`h-4 w-4 ${isChecking ? 'animate-spin' : ''}`} />
          <span>{isChecking ? 'ĐANG KIỂM TRA...' : 'THỬ LẠI KẾT NỐI'}</span>
        </button>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 px-5 py-2.5 bg-surface-container border border-surface-container-highest hover:bg-surface-container-high text-text-primary rounded-lg text-xs font-bold transition-all"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>QUAY LẠI</span>
        </button>
        <button
          onClick={() => navigate('/login')}
          className="flex items-center gap-2 px-5 py-2.5 bg-surface-container border border-surface-container-highest hover:bg-surface-container-high text-text-primary rounded-lg text-xs font-bold transition-all"
        >
          <LogIn className="h-4 w-4" />
          <span>ĐĂNG NHẬP</span>
        </button>
      </div>
    </div>
  );
};
