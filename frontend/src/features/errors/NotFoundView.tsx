import React from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import { Compass, ArrowLeft, LayoutDashboard } from 'lucide-react';

export const NotFoundView: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center px-4 py-12 text-center font-body">
      <div className="h-16 w-16 rounded-full border bg-surface-container border-surface-container-highest flex items-center justify-center mb-6">
        <Compass className="h-8 w-8 text-text-muted" />
      </div>

      <p className="text-xs font-mono text-text-muted uppercase tracking-widest mb-2">Lỗi 404</p>
      <h1 className="font-headline font-black text-2xl text-text-primary tracking-tight mb-2">Không tìm thấy trang</h1>
      <p className="text-xs text-text-secondary max-w-md mb-2 leading-relaxed">
        Không có tuyến đường nào khớp với <code className="text-text-primary">{location.pathname}</code>.
      </p>
      <p className="text-xs text-text-secondary max-w-md mb-6 leading-relaxed">
        Kiểm tra lại địa chỉ, hoặc dùng các liên kết bên dưới để quay lại.
      </p>

      <div className="flex flex-wrap items-center justify-center gap-3">
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center gap-2 px-5 py-2.5 bg-primary text-background hover:bg-primary-container rounded-lg text-xs font-bold transition-all"
        >
          <LayoutDashboard className="h-4 w-4" />
          <span>VỀ BẢNG ĐIỀU KHIỂN</span>
        </button>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 px-5 py-2.5 bg-surface-container border border-surface-container-highest hover:bg-surface-container-high text-text-primary rounded-lg text-xs font-bold transition-all"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>QUAY LẠI</span>
        </button>
      </div>
    </div>
  );
};

export default NotFoundView;
