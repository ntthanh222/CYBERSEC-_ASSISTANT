import React from 'react';
import { useNavigate } from 'react-router-dom';
import { ShieldAlert, ArrowLeft, Home } from 'lucide-react';

export const AccessDeniedView: React.FC = () => {
  const navigate = useNavigate();

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center px-4 text-center font-body">
      <div className="h-16 w-16 rounded-full bg-critical/10 border border-critical/30 flex items-center justify-center mb-6 pulse-mint">
        <ShieldAlert className="h-8 w-8 text-critical" />
      </div>

      <h1 className="font-headline font-black text-2xl text-text-primary tracking-tight mb-2">Quyền Truy cập Bị hạn chế</h1>
      <p className="text-xs font-mono text-critical uppercase tracking-widest mb-4">Lỗi 403: Quyền truy cập bị chặn</p>

      <p className="text-xs text-text-secondary max-w-md mb-8 leading-relaxed">
        Hồ sơ phiên làm việc hiện tại của bạn không có khóa mã hóa hoặc token ủy quyền quản trị cần thiết để truy vấn thư mục khu vực này.
        <br />
        <span className="block mt-2 italic text-text-muted">Liên hệ bộ phận quản trị bảo mật (admin@example.com) để thay đổi quyền hạn vai trò.</span>
      </p>

      <div className="flex gap-4">
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-2 px-4 py-2 border border-surface-container-highest hover:bg-surface-container-high rounded-lg text-xs font-medium transition-colors"
        >
          <ArrowLeft className="h-4 w-4" />
          <span>Quay lại</span>
        </button>
        <button
          onClick={() => navigate('/dashboard')}
          className="flex items-center gap-2 px-4 py-2 bg-primary text-background hover:bg-primary-container rounded-lg text-xs font-bold transition-all"
        >
          <Home className="h-4 w-4" />
          <span>Bảng điều khiển</span>
        </button>
      </div>
    </div>
  );
};
