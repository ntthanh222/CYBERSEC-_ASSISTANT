import React from 'react';
import { useNavigate } from 'react-router-dom';
import { UserCircle, LogOut, ShieldCheck, Mail, Calendar } from 'lucide-react';
import { useAuth } from '../auth/AuthContext';

export const ProfileView: React.FC = () => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  const handleLogout = async () => {
    await logout();
    navigate('/login');
  };

  return (
    <div className="space-y-6">
      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Tài khoản của tôi</h2>
        <p className="text-xs text-text-secondary">Thông tin định danh tài khoản và chi tiết phiên làm việc của người dùng đã đăng nhập.</p>
      </div>

      <div className="max-w-xl bg-surface-container border border-surface-container-highest rounded-lg p-6 space-y-4">
        <div className="flex items-center gap-3">
          <div className="h-12 w-12 rounded-full bg-primary/10 border border-primary/30 flex items-center justify-center">
            <UserCircle className="h-7 w-7 text-primary" />
          </div>
          <div>
            <p className="text-sm font-bold text-text-primary" data-testid="profile-username">{user?.username ?? '—'}</p>
            <p className="text-[10px] font-mono uppercase text-text-muted">{user?.role ?? 'user'}</p>
          </div>
        </div>

        <div className="space-y-2 pt-2 border-t border-surface-container-highest/60">
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <Mail className="h-3.5 w-3.5 text-text-muted" />
            <span data-testid="profile-email">{user?.email ?? '—'}</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-text-secondary">
            <ShieldCheck className="h-3.5 w-3.5 text-text-muted" />
            <span>Vai trò: {user?.role ?? 'user'}</span>
          </div>
          {user?.created_at && (
            <div className="flex items-center gap-2 text-xs text-text-secondary">
              <Calendar className="h-3.5 w-3.5 text-text-muted" />
              <span>Tài khoản được tạo ngày {new Date(user.created_at).toLocaleDateString()}</span>
            </div>
          )}
        </div>

        <button
          onClick={handleLogout}
          className="flex items-center gap-2 px-4 py-2 bg-critical/10 border border-critical/30 hover:bg-critical/20 text-critical rounded-lg text-xs font-bold transition-all"
        >
          <LogOut className="h-4 w-4" />
          <span>ĐĂNG XUẤT</span>
        </button>
      </div>
    </div>
  );
};

export default ProfileView;
