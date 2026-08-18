import React from 'react';
import { useNavigate } from 'react-router-dom';
import { AlertOctagon, RefreshCw, LayoutDashboard } from 'lucide-react';

export const ServerErrorView: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center px-4 py-12 text-center font-body">
      <div className="h-16 w-16 rounded-full border bg-critical/10 border-critical/30 flex items-center justify-center mb-6">
        <AlertOctagon className="h-8 w-8 text-critical" />
      </div>

      <p className="text-xs font-mono text-critical uppercase tracking-widest mb-2">Lỗi 500</p>
      <h1 className="font-headline font-black text-2xl text-text-primary tracking-tight mb-2">
        Đã xảy ra sự cố
      </h1>
      <p className="text-xs text-text-secondary max-w-md mb-6 leading-relaxed">
        Đã xảy ra lỗi ngoài dự kiến khi hiển thị trang này. Việc tải lại thường khắc phục được
        lỗi hiển thị đơn lẻ; nếu tình trạng này tiếp diễn, hệ thống backend có thể đang gặp sự cố — hãy kiểm tra
        trang Ngoại tuyến/Khôi phục để xem trạng thái trực tiếp.
      </p>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          onClick={() => window.location.reload()}
          className="flex items-center gap-2 px-5 py-2.5 bg-primary text-background hover:bg-primary-container rounded-lg text-xs font-bold transition-all"
        >
          <RefreshCw className="h-4 w-4" />
          <span>TẢI LẠI TRANG</span>
        </button>
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center gap-2 px-5 py-2.5 bg-surface-container border border-surface-container-highest hover:bg-surface-container-high text-text-primary rounded-lg text-xs font-bold transition-all"
        >
          <LayoutDashboard className="h-4 w-4" />
          <span>VỀ BẢNG ĐIỀU KHIỂN</span>
        </button>
      </div>
    </div>
  );
};

export default ServerErrorView;
