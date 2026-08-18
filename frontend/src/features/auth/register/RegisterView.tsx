import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { Shield, Eye, EyeOff, Lock, Mail, AlertTriangle, CheckCircle2 } from 'lucide-react';

export const RegisterView: React.FC = () => {
  const { register, errorMsg, infoMsg, clearError, user } = useAuth();
  const navigate = useNavigate();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || password.length < 8) return;

    setIsSubmitting(true);
    clearError();

    const success = await register(email, password);
    setIsSubmitting(false);

    if (success && user) {
      navigate('/dashboard');
    }
  };

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center px-4 font-body">

      <div className="flex items-center gap-3 mb-8">
        <div className="h-12 w-12 rounded bg-primary/20 flex items-center justify-center border border-primary/40 pulse-mint">
          <Shield className="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 className="font-headline font-black text-2xl tracking-tight text-text-primary leading-none">CyberSec Assistant</h1>
          <span className="text-xs text-text-muted font-mono tracking-wider uppercase">Không gian làm việc CyberSec Assistant</span>
        </div>
      </div>

      <div className="w-full max-w-md bg-surface-container border border-surface-container-highest rounded-xl p-6 md:p-8 shadow-elevated">
        <h2 className="font-headline font-bold text-lg text-text-primary mb-2">Tạo tài khoản Security Console</h2>
        <p className="text-xs text-text-secondary mb-6 leading-relaxed">
          Đăng ký tài khoản mới qua Supabase Auth. Mật khẩu phải có ít nhất 8 ký tự.
        </p>

        {errorMsg && (
          <div className="mb-6 bg-critical/10 border border-critical/30 rounded-lg p-3 flex items-start gap-2 text-xs text-critical">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}
        {infoMsg && (
          <div className="mb-6 bg-primary/10 border border-primary/30 rounded-lg p-3 flex items-start gap-2 text-xs text-primary">
            <CheckCircle2 className="h-4 w-4 mt-0.5 shrink-0" />
            <span>{infoMsg}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">

          <div className="space-y-1.5">
            <label className="text-[10px] font-mono tracking-wider uppercase text-text-muted" htmlFor="register-email-input">
              Định danh tài khoản (Email)
            </label>
            <div className="relative flex items-center">
              <Mail className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
              <input
                id="register-email-input"
                type="email"
                required
                value={email}
                onChange={(e) => { setEmail(e.target.value); clearError(); }}
                placeholder="you@example.com"
                className="w-full bg-surface-container-low border border-surface-container-highest rounded-lg py-2 pl-10 pr-4 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 transition-all"
              />
            </div>
          </div>

          <div className="space-y-1.5">
            <label className="text-[10px] font-mono tracking-wider uppercase text-text-muted" htmlFor="register-password-input">
              Mật khẩu (tối thiểu 8 ký tự)
            </label>
            <div className="relative flex items-center">
              <Lock className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
              <input
                id="register-password-input"
                type={showPassword ? 'text' : 'password'}
                required
                minLength={8}
                value={password}
                onChange={(e) => { setPassword(e.target.value); clearError(); }}
                placeholder="••••••••••••"
                autoComplete="new-password"
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

          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full mt-2 bg-primary text-background font-headline font-bold text-xs py-2.5 rounded-lg hover:bg-primary-container active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center gap-2"
          >
            {isSubmitting ? 'ĐANG ĐĂNG KÝ...' : 'TẠO TÀI KHOẢN'}
          </button>

        </form>

        <div className="mt-6 text-center text-xs text-text-secondary">
          Đã có tài khoản?{' '}
          <Link to="/login" className="text-primary hover:underline font-semibold">
            Đăng nhập
          </Link>
        </div>

      </div>
    </div>
  );
};
export default RegisterView;
