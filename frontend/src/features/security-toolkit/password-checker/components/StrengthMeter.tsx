import React from 'react';
import { Check, X } from 'lucide-react';

interface StrengthMeterProps {
  score: number; // 0 to 4
  strengthLabel: 'weak' | 'medium' | 'strong' | 'very_strong' | 'empty';
  criteria: {
    length: boolean;
    upper: boolean;
    lower: boolean;
    number: boolean;
    symbol: boolean;
  };
}

export const StrengthMeter: React.FC<StrengthMeterProps> = ({
  score,
  strengthLabel,
  criteria
}) => {
  const getStrengthConfig = () => {
    switch (strengthLabel) {
      case 'weak':
        return { color: 'bg-critical', text: 'YẾU', desc: 'Rất dễ bị tấn công brute force.' };
      case 'medium':
        return { color: 'bg-warning', text: 'TRUNG BÌNH', desc: 'Đạt yêu cầu tối thiểu nhưng vẫn có nguy cơ bị tấn công từ điển.' };
      case 'strong':
        return { color: 'bg-info', text: 'MẠNH', desc: 'An toàn. Phù hợp cho tài khoản nhân viên thông thường.' };
      case 'very_strong':
        return { color: 'bg-success', text: 'XUẤT SẮC', desc: 'Cực kỳ an toàn. Lý tưởng cho tài khoản quản trị cấp cao.' };
      case 'empty':
      default:
        return { color: 'bg-surface-container-highest', text: 'TRỐNG', desc: 'Nhập mật khẩu để kiểm tra.' };
    }
  };

  const config = getStrengthConfig();

  const criteriaList = [
    { key: 'length', label: 'Tối thiểu 10 ký tự' },
    { key: 'upper', label: 'Ít nhất một chữ HOA' },
    { key: 'lower', label: 'Ít nhất một chữ thường' },
    { key: 'number', label: 'Ít nhất một chữ số' },
    { key: 'symbol', label: 'Ít nhất một ký tự đặc biệt (!@#$%^&*)' }
  ];

  return (
    <div className="space-y-4">
      
      {/* Strength Bar indicators */}
      <div className="space-y-1.5 font-mono">
        <div className="flex justify-between items-center text-[10px]">
          <span className="text-text-secondary uppercase">Đánh giá độ phức tạp mật khẩu</span>
          <span className={`font-bold ${
            strengthLabel === 'weak' ? 'text-critical' :
            strengthLabel === 'medium' ? 'text-warning' :
            strengthLabel === 'strong' ? 'text-info' :
            strengthLabel === 'very_strong' ? 'text-success' : 'text-text-muted'
          }`}>{config.text}</span>
        </div>

        {/* Strength Progress Bars */}
        <div className="grid grid-cols-4 gap-1.5 h-2 w-full">
          {[1, 2, 3, 4].map((step) => {
            const active = score >= step;
            return (
              <div 
                key={step} 
                className={`h-full rounded-full transition-all duration-300 ${
                  active ? config.color : 'bg-surface-container-highest'
                }`}
              />
            );
          })}
        </div>
        <p className="text-[10px] text-text-muted mt-1">{config.desc}</p>
      </div>

      {/* Criteria check lists */}
      <div className="space-y-2 pt-2 border-t border-surface-container-highest/60">
        <span className="text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold block">Danh sách tiêu chí bảo mật</span>
        
        <div className="space-y-1.5">
          {criteriaList.map((item) => {
            const met = (criteria as any)[item.key];
            return (
              <div 
                key={item.key} 
                className="flex items-center justify-between text-xs font-mono bg-background/30 px-3 py-1.5 rounded border border-surface-container-highest/20"
              >
                <span className={met ? 'text-text-primary' : 'text-text-muted'}>{item.label}</span>
                <span className={met ? 'text-success' : 'text-text-muted'}>
                  {met ? <Check className="h-4 w-4" /> : <X className="h-4 w-4" />}
                </span>
              </div>
            );
          })}
        </div>

      </div>

    </div>
  );
};
