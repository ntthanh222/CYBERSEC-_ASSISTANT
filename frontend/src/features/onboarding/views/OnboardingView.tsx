import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { CheckCircle2, Circle, Compass } from 'lucide-react';

const STORAGE_KEY = 'onboarding-completed-steps';

interface OnboardingStep {
  id: string;
  title: string;
  description: string;
  path: string;
  cta: string;
}

const STEPS: OnboardingStep[] = [
  {
    id: 'dashboard',
    title: 'Xem qua Dashboard',
    description: 'Xem số liệu thực tế theo từng tài khoản về tài liệu, cuộc trò chuyện, lượt quét và hoạt động gần đây.',
    path: '/dashboard',
    cta: 'Mở Dashboard',
  },
  {
    id: 'assistant',
    title: 'Hỏi AI Assistant',
    description: 'Đặt câu hỏi bảo mật hoặc thực hiện tra cứu qua khung chat trợ lý.',
    path: '/ai',
    cta: 'Mở AI Assistant',
  },
  {
    id: 'assets',
    title: 'Thêm tài sản đầu tiên',
    description: 'Theo dõi các hệ thống bạn sở hữu trong Asset Inventory.',
    path: '/assets',
    cta: 'Mở Assets Inventory',
  },
  {
    id: 'threat-intel',
    title: 'Khám phá Threat Intel',
    description: 'Duyệt các chỉ báo xâm phạm (IOC) và thêm một mục vào danh sách theo dõi của bạn.',
    path: '/threat-intel',
    cta: 'Mở Threat Intel',
  },
  {
    id: 'reports',
    title: 'Tạo báo cáo',
    description: 'Tạo báo cáo từ một mẫu có sẵn trong Reports Center.',
    path: '/reports/builder',
    cta: 'Mở công cụ tạo báo cáo',
  },
];

function readCompleted(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

export const OnboardingView: React.FC = () => {
  const [completed, setCompleted] = useState<Set<string>>(() => readCompleted());

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(completed)));
    } catch {
      // localStorage unavailable (private browsing, quota) - progress just won't persist.
    }
  }, [completed]);

  const toggleStep = (id: string) => {
    setCompleted((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const completedCount = completed.size;

  return (
    <div className="space-y-6">
      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">
          Bắt đầu
        </h2>
        <p className="text-xs text-text-secondary">
          Đã hoàn thành {completedCount} / {STEPS.length} bước
        </p>
      </div>

      <ul className="space-y-3 max-w-2xl">
        {STEPS.map((step) => {
          const isDone = completed.has(step.id);
          return (
            <li
              key={step.id}
              data-testid={`onboarding-step-${step.id}`}
              className="flex items-start gap-3 bg-surface-container border border-surface-container-highest rounded-lg p-4"
            >
              <button
                onClick={() => toggleStep(step.id)}
                aria-label={isDone ? `Đánh dấu ${step.title} là chưa hoàn thành` : `Đánh dấu ${step.title} là đã hoàn thành`}
                className="mt-0.5 shrink-0"
              >
                {isDone ? (
                  <CheckCircle2 className="h-5 w-5 text-primary" />
                ) : (
                  <Circle className="h-5 w-5 text-text-muted" />
                )}
              </button>
              <div className="flex-1 space-y-1">
                <p className={`text-sm font-bold ${isDone ? 'text-text-muted line-through' : 'text-text-primary'}`}>
                  {step.title}
                </p>
                <p className="text-xs text-text-secondary">{step.description}</p>
                <Link
                  to={step.path}
                  className="inline-flex items-center gap-1 text-xs text-primary hover:underline mt-1"
                >
                  <Compass className="h-3.5 w-3.5" />
                  {step.cta}
                </Link>
              </div>
            </li>
          );
        })}
      </ul>
    </div>
  );
};

export default OnboardingView;
