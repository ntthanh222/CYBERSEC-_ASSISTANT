import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Shield, Lock, Eye, EyeOff, AlertTriangle, ArrowLeft } from 'lucide-react';

export const ResetPasswordView: React.FC = () => {

  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitted, setIsSubmitted] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Password reset is not implemented in this build - no reset-token
  // backend endpoint exists, this page never reads a token from the URL,
  // and no network call is ever made. Field-level validation below is real
  // client-side validation, not a fake save; the notice shown on submit
  // makes clear nothing was actually changed.
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!password || !confirmPassword) return;

    if (password.length < 8) {
      setErrorMsg('Mật khẩu phải có ít nhất 8 ký tự.');
      return;
    }

    if (password !== confirmPassword) {
      setErrorMsg('Mật khẩu không khớp.');
      return;
    }

    setErrorMsg(null);
    setIsSubmitted(true);
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center px-4 font-body">
      
      {/* Branding */}
      <div className="flex items-center gap-3 mb-8">
        <div className="h-12 w-12 rounded bg-primary/20 flex items-center justify-center border border-primary/40 pulse-mint">
          <Shield className="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 className="font-headline font-black text-2xl tracking-tight text-text-primary leading-none">CyberSec Assistant</h1>
          <span className="text-xs text-text-muted font-mono tracking-wider uppercase">Không gian làm việc CyberSec Assistant</span>
        </div>
      </div>

      {/* Card Form */}
      <div className="w-full max-w-md bg-surface-container border border-surface-container-highest rounded-xl p-6 md:p-8 shadow-elevated">
        <h2 className="font-headline font-bold text-lg text-text-primary mb-2">Đặt lại mật khẩu</h2>

        {!isSubmitted ? (
          <>
            <p className="text-xs text-text-secondary mb-6 leading-relaxed">
              Chức năng đặt lại mật khẩu chưa được triển khai trong bản build này. Biểu mẫu này chỉ xác thực dữ liệu cục bộ và sẽ không lưu hoặc gửi đi bất kỳ thứ gì.
            </p>

            {errorMsg && (
              <div className="mb-4 bg-critical/10 border border-critical/30 rounded-lg p-2.5 text-xs text-critical">
                {errorMsg}
              </div>
            )}

            <form onSubmit={handleSubmit} className="space-y-4">
              
              <div className="space-y-1.5">
                <label className="text-[10px] font-mono tracking-wider uppercase text-text-muted" htmlFor="new-password">
                  Mật khẩu bảo mật mới
                </label>
                <div className="relative flex items-center">
                  <Lock className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
                  <input 
                    id="new-password"
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full bg-surface-container-low border border-surface-container-highest rounded-lg py-2 pl-10 pr-10 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 transition-all"
                  />
                  <button
                    type="button"
                    className="absolute right-3 text-text-muted hover:text-text-primary"
                    onClick={() => setShowPassword(!showPassword)}
                    aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-[10px] font-mono tracking-wider uppercase text-text-muted" htmlFor="confirm-password">
                  Xác nhận mật khẩu
                </label>
                <div className="relative flex items-center">
                  <Lock className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
                  <input 
                    id="confirm-password"
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••••••"
                    className="w-full bg-surface-container-low border border-surface-container-highest rounded-lg py-2 pl-10 pr-10 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 transition-all"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="w-full mt-2 bg-primary text-background font-headline font-bold text-xs py-2.5 rounded-lg hover:bg-primary-container active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center font-bold"
              >
                TIẾP TỤC
              </button>

            </form>
          </>
        ) : (
          <div className="text-center py-4 space-y-4">
            <div className="mx-auto h-12 w-12 rounded-full bg-warning/15 border border-warning/30 flex items-center justify-center">
              <AlertTriangle className="h-6 w-6 text-warning" />
            </div>
            <h3 className="font-headline font-bold text-sm text-text-primary">Chức năng đặt lại mật khẩu chưa khả dụng</h3>
            <p className="text-xs text-text-secondary leading-relaxed px-4">
              Chức năng đặt lại mật khẩu chưa được triển khai trong bản build này. Thông tin đăng nhập của bạn chưa thay đổi. Hãy liên hệ quản trị viên để đặt lại thông tin đăng nhập.
            </p>
            <div className="pt-2">
              <Link
                to="/login"
                className="inline-block bg-primary text-background font-headline font-bold text-xs px-6 py-2 rounded-lg hover:bg-primary-container transition-all"
              >
                Đến trang đăng nhập
              </Link>
            </div>
          </div>
        )}

        {/* Back Link */}
        {!isSubmitted && (
          <div className="mt-6 pt-4 border-t border-surface-container-highest/60 flex justify-center">
            <Link
              to="/login"
              className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary transition-colors font-mono uppercase tracking-wider text-[10px]"
            >
              <ArrowLeft className="h-3 w-3" />
              <span>Hủy & quay lại</span>
            </Link>
          </div>
        )}

      </div>

    </div>
  );
};
