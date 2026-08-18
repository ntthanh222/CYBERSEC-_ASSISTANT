import React, { useEffect, useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { isSupabaseConfigured } from '../../../lib/supabase/authService';
import { getMe } from '../../../lib/api/auth';
import {
  Shield,
  ShieldPlus,
  Eye,
  EyeOff,
  Lock,
  User as UserIcon,
  AlertTriangle,
} from 'lucide-react';

/** Where to land after a successful sign-in, based on the account's real
 * DB-backed role (never assumed from which form was used) - an admin or
 * super_admin goes straight to the administration overview, everyone else
 * to the regular dashboard. Reads role fresh via `/api/auth/me` rather than
 * trusting AuthContext's still-stale `user` (React state set inside the
 * login call hasn't re-rendered yet by the time the awaited call returns). */
async function redirectAfterLogin(navigate: ReturnType<typeof useNavigate>): Promise<void> {
  try {
    const me = await getMe();
    if (me.role === 'admin' || me.role === 'super_admin') {
      navigate('/admin/overview');
      return;
    }
  } catch {
    // Fall through to the default landing page - a role lookup failure
    // must never block getting the user into the app at all.
  }
  navigate('/dashboard');
}

export const LoginView: React.FC = () => {
  const { login, setupAdmin, checkAdminSetupNeeded, errorMsg, clearError, isSessionExpired } = useAuth();
  const navigate = useNavigate();

  // Single visible sign-in field: accepts either an email (hosted Supabase
  // deployments) or a local account username (Docker-local deployments) -
  // AuthContext.login() decides which backend to call, never this form.
  const [identifier, setIdentifier] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // First-run administrator setup - folded into this single /login page
  // (no more separate /admin/setup page) rather than a distinct route, so
  // there is exactly one entry point regardless of account state.
  const [setupNeeded, setSetupNeeded] = useState(false);
  const [setupUsername, setSetupUsername] = useState('');
  const [setupPassword, setSetupPassword] = useState('');
  const [setupConfirmPassword, setSetupConfirmPassword] = useState('');
  const [setupLocalError, setSetupLocalError] = useState<string | null>(null);
  const [isSettingUp, setIsSettingUp] = useState(false);

  useEffect(() => {
    let cancelled = false;
    // Non-blocking: the normal login form renders immediately regardless
    // (a hosted-Supabase deployment must never wait on this local-only
    // check), and only swaps to the setup form if/when this resolves true.
    checkAdminSetupNeeded().then((needsSetup) => {
      if (!cancelled && needsSetup) setSetupNeeded(true);
    });
    return () => {
      cancelled = true;
    };
  }, [checkAdminSetupNeeded]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!identifier || !password) return;

    setIsSubmitting(true);
    clearError();

    const success = await login(identifier, password);
    setIsSubmitting(false);

    if (success) await redirectAfterLogin(navigate);
  };

  const handleSetupSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSetupLocalError(null);
    if (setupPassword.length < 8) {
      setSetupLocalError('Mật khẩu phải có ít nhất 8 ký tự.');
      return;
    }
    if (setupPassword !== setupConfirmPassword) {
      setSetupLocalError('Mật khẩu không khớp.');
      return;
    }

    setIsSettingUp(true);
    clearError();
    const success = await setupAdmin(setupUsername, setupPassword);
    setIsSettingUp(false);

    if (success) navigate('/admin/overview');
  };

  if (setupNeeded) {
    return (
      <div className="min-h-screen bg-background flex flex-col justify-center items-center px-4 font-body">
        <div className="flex items-center gap-3 mb-8">
          <div className="h-12 w-12 rounded bg-primary/20 flex items-center justify-center border border-primary/40">
            <ShieldPlus className="h-6 w-6 text-primary" />
          </div>
          <div>
            <h1 className="font-headline font-black text-2xl tracking-tight text-text-primary leading-none">
              THIẾT LẬP QUẢN TRỊ VIÊN LẦN ĐẦU
            </h1>
            <span className="text-xs text-text-muted font-mono tracking-wider uppercase">
              CyberSec Assistant - tạo tài khoản quản trị viên cục bộ
            </span>
          </div>
        </div>

        <div className="w-full max-w-md bg-surface-container border border-surface-container-highest rounded-xl p-6 md:p-8 shadow-elevated">
          <p className="text-xs text-text-secondary mb-6 leading-relaxed">
            Chưa có tài khoản quản trị viên nào. Hãy tạo một tài khoản ngay - thao tác này chỉ thực
            hiện được một lần; mọi lần đăng nhập sau đều dùng thông tin này. Không có dữ liệu nào
            được gửi ra bên ngoài hệ thống cục bộ này.
          </p>

          {(setupLocalError || errorMsg) && (
            <div className="mb-6 bg-critical/10 border border-critical/30 rounded-lg p-3 flex items-start gap-2 text-xs text-critical">
              <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
              <span>{setupLocalError ?? errorMsg}</span>
            </div>
          )}

          <form onSubmit={handleSetupSubmit} className="space-y-4">
            <div className="space-y-1.5">
              <label
                className="text-[10px] font-mono tracking-wider uppercase text-text-muted"
                htmlFor="setup-username-input"
              >
                Tên đăng nhập quản trị viên
              </label>
              <div className="relative flex items-center">
                <UserIcon className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
                <input
                  id="setup-username-input"
                  type="text"
                  required
                  minLength={3}
                  maxLength={64}
                  value={setupUsername}
                  onChange={(e) => {
                    setSetupUsername(e.target.value);
                    clearError();
                    setSetupLocalError(null);
                  }}
                  autoComplete="username"
                  className="w-full bg-surface-container-low border border-surface-container-highest rounded-lg py-2 pl-10 pr-4 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 transition-all"
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <label
                className="text-[10px] font-mono tracking-wider uppercase text-text-muted"
                htmlFor="setup-password-input"
              >
                Mật khẩu (tối thiểu 8 ký tự)
              </label>
              <div className="relative flex items-center">
                <Lock className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
                <input
                  id="setup-password-input"
                  type={showPassword ? 'text' : 'password'}
                  required
                  minLength={8}
                  value={setupPassword}
                  onChange={(e) => setSetupPassword(e.target.value)}
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

            <div className="space-y-1.5">
              <label
                className="text-[10px] font-mono tracking-wider uppercase text-text-muted"
                htmlFor="setup-confirm-input"
              >
                Xác nhận mật khẩu
              </label>
              <div className="relative flex items-center">
                <Lock className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
                <input
                  id="setup-confirm-input"
                  type={showPassword ? 'text' : 'password'}
                  required
                  value={setupConfirmPassword}
                  onChange={(e) => setSetupConfirmPassword(e.target.value)}
                  autoComplete="new-password"
                  className="w-full bg-surface-container-low border border-surface-container-highest rounded-lg py-2 pl-10 pr-4 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 transition-all"
                />
              </div>
            </div>

            <button
              type="submit"
              disabled={isSettingUp}
              className="w-full mt-2 bg-primary text-background font-headline font-bold text-xs py-2.5 rounded-lg hover:bg-primary-container active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none"
            >
              {isSettingUp ? 'ĐANG TẠO QUẢN TRỊ VIÊN...' : 'TẠO TÀI KHOẢN QUẢN TRỊ'}
            </button>
          </form>

          <div className="mt-6 text-center text-xs text-text-secondary">
            <button
              type="button"
              onClick={() => setSetupNeeded(false)}
              className="text-primary hover:underline font-semibold"
            >
              Tôi đã có tài khoản - quay lại đăng nhập
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-background flex flex-col justify-center items-center px-4 font-body">
      {/* Branding */}
      <div className="flex items-center gap-3 mb-8">
        <div className="h-12 w-12 rounded bg-primary/20 flex items-center justify-center border border-primary/40 pulse-mint">
          <Shield className="h-6 w-6 text-primary" />
        </div>
        <div>
          <h1 className="font-headline font-black text-2xl tracking-tight text-text-primary leading-none">
            CyberSec Assistant
          </h1>
          <span className="text-xs text-text-muted font-mono tracking-wider uppercase">
            Security Console
          </span>
        </div>
      </div>

      {/* Card Form */}
      <div className="w-full max-w-md bg-surface-container border border-surface-container-highest rounded-xl p-6 md:p-8 shadow-elevated">
        <h2 className="font-headline font-bold text-lg text-text-primary mb-2">Truy cập Security Console</h2>
        <p className="text-xs text-text-secondary mb-6 leading-relaxed">
          Vui lòng xác thực thông tin đăng nhập để thiết lập phiên bảo mật.
        </p>

        {errorMsg && (
          <div className="mb-6 bg-critical/10 border border-critical/30 rounded-lg p-3 flex items-start gap-2 text-xs text-critical">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {isSessionExpired && !errorMsg && (
          <div className="mb-6 bg-warning/10 border border-warning/30 rounded-lg p-3 flex items-start gap-2 text-xs text-warning">
            <AlertTriangle className="h-4 w-4 mt-0.5 shrink-0" />
            <span>Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Identity input - accepts either an email (hosted deployments)
              or a local account username (Docker-local deployments); which
              backend actually verifies it is decided server-side by
              AuthContext.login(), never by anything typed here. */}
          <div className="space-y-1.5">
            <label className="text-[10px] font-mono tracking-wider uppercase text-text-muted" htmlFor="identifier-input">
              Tên đăng nhập hoặc Email
            </label>
            <div className="relative flex items-center">
              <UserIcon className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
              <input
                id="identifier-input"
                type="text"
                required
                value={identifier}
                onChange={(e) => {
                  setIdentifier(e.target.value);
                  clearError();
                }}
                placeholder="you@example.com hoặc demo_user"
                autoComplete="username"
                className="w-full bg-surface-container-low border border-surface-container-highest rounded-lg py-2 pl-10 pr-4 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 transition-all"
              />
            </div>
          </div>

          {/* Password input */}
          <div className="space-y-1.5">
            <label className="text-[10px] font-mono tracking-wider uppercase text-text-muted" htmlFor="password-input">
              Mật khẩu
            </label>
            <div className="relative flex items-center">
              <Lock className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
              <input
                id="password-input"
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                autoComplete="current-password"
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

          {/* Submit button */}
          <button
            type="submit"
            disabled={isSubmitting}
            className="w-full mt-2 bg-primary text-background font-headline font-bold text-xs py-2.5 rounded-lg hover:bg-primary-container active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center gap-2"
          >
            {isSubmitting ? 'ĐANG KẾT NỐI...' : 'THIẾT LẬP PHIÊN BẢO MẬT'}
          </button>
        </form>

        {isSupabaseConfigured() && (
          <div className="mt-6 text-center text-xs text-text-secondary">
            Chưa có tài khoản?{' '}
            <Link to="/register" className="text-primary hover:underline font-semibold">
              Đăng ký
            </Link>
          </div>
        )}
      </div>

      <div className="mt-8 text-center text-[10px] text-text-muted font-mono tracking-wider">
        <span>CẢNH BÁO BẢO MẬT: HỆ THỐNG ĐANG GIÁM SÁT TRUY CẬP.</span>
      </div>
    </div>
  );
};
