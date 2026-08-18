import React, { useState, useEffect } from 'react';
import { ToolkitLayout } from '../../shared/ToolkitLayout';
import { StrengthMeter } from '../components/StrengthMeter';
import { checkPasswordStrength } from '../../../../lib/api/tools';
import type { PasswordCheckResponse } from '../../../../lib/api/tools';
import { ApiError } from '../../../../lib/api/client';
import { Eye, EyeOff, Lock, RefreshCw, AlertTriangle, KeyRound } from 'lucide-react';

export const PasswordCheckerView: React.FC = () => {
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PasswordCheckResponse | null>(null);

  useEffect(() => {
    if (!password) {
      setResult(null);
      setError(null);
      return;
    }

    setLoading(true);
    let cancelled = false;

    const checkTimeout = setTimeout(() => {
      checkPasswordStrength(password)
        .then((res) => {
          if (cancelled) return;
          setResult(res);
          setError(null);
        })
        .catch((err) => {
          if (cancelled) return;
          setError(err instanceof ApiError ? err.message : 'Không thể kết nối tới công cụ kiểm tra mật khẩu.');
          setResult(null);
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 300); // debounce typing

    return () => {
      cancelled = true;
      clearTimeout(checkTimeout);
    };
  }, [password]);

  const handleReset = () => {
    setPassword('');
  };

  const strengthLabel = result?.strength ?? 'empty';
  const criteria = {
    length: result ? result.length >= 10 : false,
    upper: result?.has_uppercase ?? false,
    lower: result?.has_lowercase ?? false,
    number: result?.has_digits ?? false,
    symbol: result?.has_special ?? false,
  };

  return (
    <ToolkitLayout title="Kiểm tra Mật khẩu" subtitle="Đánh giá độ mạnh mật khẩu ngay trên thiết bị, không lưu trữ.">
      <div className="space-y-6 max-w-3xl mx-auto">

        {/* Security Notice */}
        <div className="bg-warning/5 border border-warning/20 p-3.5 rounded-lg flex items-start gap-2.5 text-xs text-warning leading-relaxed font-mono">
          <AlertTriangle className="h-4.5 w-4.5 shrink-0 mt-0.5" />
          <div>
            <span className="font-bold block uppercase mb-1">Phân tích phía máy chủ, không lưu trữ</span>
            <p className="text-[11px] text-text-secondary">
              Chỉ được backend phân tích trong bộ nhớ tạm - không bao giờ được lưu trữ, ghi nhật ký, gửi lại, hay
              dùng làm nhãn số liệu. Mật khẩu không bao giờ xuất hiện trong lịch sử quét.
            </p>
          </div>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">

          <div className="space-y-4">

            <div className="space-y-1.5">
              <label className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold" htmlFor="pass-checker-input">
                Nhập mật khẩu
              </label>
              <div className="relative flex items-center bg-background border border-surface-container-highest focus-within:ring-1 focus-within:ring-primary/40 focus-within:border-primary/40 rounded-lg p-1.5 transition-all">
                <Lock className="h-4 w-4 text-text-muted absolute left-3.5 pointer-events-none" />
                <input
                  id="pass-checker-input"
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="Nhập mật khẩu để kiểm tra..."
                  autoComplete="new-password"
                  className="w-full bg-transparent border-none py-1.5 pl-10 pr-20 text-xs text-text-primary placeholder:text-text-muted focus:outline-none"
                />
                <div className="absolute right-2 flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="p-1.5 hover:bg-surface-container-high rounded text-text-muted hover:text-text-primary"
                    aria-label={showPassword ? 'Ẩn mật khẩu' : 'Hiện mật khẩu'}
                  >
                    {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                  <button
                    type="button"
                    onClick={handleReset}
                    className="px-2 py-1 hover:bg-surface-container-high rounded text-[9px] font-mono text-text-secondary"
                  >
                    ĐẶT LẠI
                  </button>
                </div>
              </div>
            </div>

            <StrengthMeter score={result?.score ?? 0} strengthLabel={strengthLabel} criteria={criteria} />

          </div>

          <div className="bg-background/25 border border-surface-container-highest p-5 rounded-lg flex flex-col justify-center min-h-[250px]">

            {loading ? (
              <div className="flex flex-col items-center justify-center text-center py-8 space-y-2 font-mono">
                <RefreshCw className="h-6 w-6 text-primary animate-spin" />
                <span className="text-[10px] text-text-muted uppercase">Đang tính toán chỉ số entropy...</span>
              </div>
            ) : error ? (
              <div className="flex flex-col items-center justify-center text-center py-8 space-y-2 font-mono text-critical">
                <AlertTriangle className="h-6 w-6" />
                <span className="text-[10px] uppercase">{error}</span>
              </div>
            ) : result ? (
              <div className="space-y-5 animate-fade-in font-mono text-xs">

                <div className="bg-surface-container border border-surface-container-highest p-4 rounded-lg text-center space-y-1">
                  <span className="text-[9px] text-text-muted uppercase tracking-widest block font-bold">Thời gian ước tính để dò mật khẩu (Brute Force)</span>
                  <span className="text-xl font-headline font-black text-primary block py-1">{result.crack_time}</span>
                  <span className="text-[9px] text-text-muted leading-relaxed block">
                    Entropy: {result.entropy_bits.toFixed(1)} bit · {result.character_classes} nhóm ký tự
                  </span>
                </div>

                {result.warnings.length > 0 && (
                  <div className="space-y-2">
                    <span className="text-[9px] text-warning uppercase tracking-widest block font-bold">Cảnh báo</span>
                    <ul className="space-y-1.5 text-[10px] text-warning">
                      {result.warnings.map((warning, idx) => (
                        <li key={idx} className="flex items-start gap-1.5">
                          <span className="mt-0.5">•</span>
                          <span>{warning}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                <div className="space-y-2">
                  <span className="text-[9px] text-text-muted uppercase tracking-widest block font-bold">Hướng dẫn khắc phục</span>
                  <ul className="space-y-1.5 text-[10px] text-text-secondary">
                    {result.recommendations.map((rec, idx) => (
                      <li key={idx} className="flex items-start gap-1.5">
                        <span className="text-primary mt-0.5">•</span>
                        <span>{rec}</span>
                      </li>
                    ))}
                  </ul>
                </div>

              </div>
            ) : (
              <div className="text-center text-text-muted space-y-2 py-8">
                <KeyRound className="h-10 w-10 mx-auto opacity-30" />
                <p className="text-xs">Chưa có mật khẩu nào được đánh giá.</p>
              </div>
            )}

          </div>

        </div>

      </div>
    </ToolkitLayout>
  );
};
export default PasswordCheckerView;
