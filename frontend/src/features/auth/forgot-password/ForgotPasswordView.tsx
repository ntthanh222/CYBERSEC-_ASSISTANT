import React, { useState } from 'react';
import { Link } from 'react-router-dom';
import { Shield, Mail, ArrowLeft } from 'lucide-react';

export const ForgotPasswordView: React.FC = () => {
  const [email, setEmail] = useState('');
  const [isSubmitted, setIsSubmitted] = useState(false);

  // Password-reset email delivery is not implemented in this build - no
  // backend endpoint exists for it, and no network call is ever made. The
  // notice below is shown immediately on submit; there is no "sending"
  // state to fake, since nothing is actually sent.
  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!email) return;
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
        <h2 className="font-headline font-bold text-lg text-text-primary mb-2">Khôi phục mật khẩu</h2>

        {!isSubmitted ? (
          <>
            <p className="text-xs text-text-secondary mb-6 leading-relaxed">
              Chức năng khôi phục mật khẩu qua email chưa được triển khai trong bản build này. Gửi biểu mẫu này sẽ không gửi đi bất kỳ thứ gì.
            </p>

            <form onSubmit={handleSubmit} className="space-y-4">

              <div className="space-y-1.5">
                <label className="text-[10px] font-mono tracking-wider uppercase text-text-muted" htmlFor="email-input">
                  Email công ty đã đăng ký
                </label>
                <div className="relative flex items-center">
                  <Mail className="h-4 w-4 text-text-muted absolute left-3 pointer-events-none" />
                  <input 
                    id="email-input"
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="you@example.com"
                    className="w-full bg-surface-container-low border border-surface-container-highest rounded-lg py-2 pl-10 pr-4 text-xs text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 transition-all"
                  />
                </div>
              </div>

              <button
                type="submit"
                className="w-full mt-2 bg-primary text-background font-headline font-bold text-xs py-2.5 rounded-lg hover:bg-primary-container active:scale-[0.98] transition-all disabled:opacity-50 disabled:pointer-events-none flex items-center justify-center"
              >
                TIẾP TỤC
              </button>

            </form>
          </>
        ) : (
          <div className="text-center py-4 space-y-4">
            <div className="mx-auto h-12 w-12 rounded-full bg-warning/15 border border-warning/30 flex items-center justify-center">
              <Mail className="h-6 w-6 text-warning" />
            </div>
            <h3 className="font-headline font-bold text-sm text-text-primary">Chức năng khôi phục mật khẩu chưa khả dụng</h3>
            <p className="text-xs text-text-secondary leading-relaxed px-4">
              Chức năng khôi phục mật khẩu qua email chưa được triển khai trong bản build này. Không có email nào được gửi tới <span className="text-text-primary font-bold">{email}</span>. Hãy liên hệ quản trị viên để đặt lại thông tin đăng nhập của bạn.
            </p>
          </div>
        )}

        {/* Back Link */}
        <div className="mt-6 pt-4 border-t border-surface-container-highest/60 flex justify-center">
          <Link 
            to="/login" 
            className="flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary transition-colors font-mono uppercase tracking-wider text-[10px]"
          >
            <ArrowLeft className="h-3 w-3" />
            <span>Quay lại đăng nhập</span>
          </Link>
        </div>

      </div>

    </div>
  );
};
