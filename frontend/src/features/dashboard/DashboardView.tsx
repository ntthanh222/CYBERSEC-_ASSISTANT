import React, { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { getDashboardSummary } from '../../lib/api/dashboard';
import type { DashboardSummaryResponse } from '../../lib/api/dashboard';
import { getSystemHealth } from '../../lib/api/system';
import type { SystemHealthResponse } from '../../lib/api/system';
import { ApiError } from '../../lib/api/client';
import {
  MessageSquare, ShieldCheck,
  ArrowUpRight, ChevronRight, RotateCw, FileText, Search
} from 'lucide-react';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; summary: DashboardSummaryResponse; health: SystemHealthResponse | null };

const ACTIVITY_LABEL: Record<string, string> = {
  conversation: 'Cuộc trò chuyện AI',
  document: 'Tài liệu Knowledge Base',
  scan: 'Quét bảo mật',
};

function formatRelativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diffSeconds = Math.max(0, Math.round((Date.now() - then) / 1000));
  if (diffSeconds < 60) return `${diffSeconds} giây trước`;
  const diffMinutes = Math.round(diffSeconds / 60);
  if (diffMinutes < 60) return `${diffMinutes} phút trước`;
  const diffHours = Math.round(diffMinutes / 60);
  if (diffHours < 24) return `${diffHours} giờ trước`;
  const diffDays = Math.round(diffHours / 24);
  return `${diffDays} ngày trước`;
}

export const DashboardView: React.FC = () => {
  const navigate = useNavigate();
  const [state, setState] = useState<LoadState>({ status: 'loading' });

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      const [summary, health] = await Promise.all([
        getDashboardSummary(),
        // Health is informative, not blocking - a degraded/unreachable
        // health probe must never hide the (still real) counts and activity.
        getSystemHealth().catch(() => null),
      ]);
      setState({ status: 'ready', summary, health });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Không thể kết nối đến backend.';
      setState({ status: 'error', message });
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  if (state.status === 'loading') {
    return (
      <div className="space-y-6 animate-pulse p-4">
        <div className="h-8 bg-surface-container-high rounded w-1/4"></div>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
          <div className="h-24 bg-surface-container-high rounded-xl"></div>
          <div className="h-24 bg-surface-container-high rounded-xl"></div>
          <div className="h-24 bg-surface-container-high rounded-xl"></div>
          <div className="h-24 bg-surface-container-high rounded-xl"></div>
        </div>
        <div className="h-64 bg-surface-container-high rounded-xl"></div>
      </div>
    );
  }

  if (state.status === 'error') {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
        <p className="text-sm text-text-secondary">
          Không thể tải dữ liệu Dashboard: {state.message}
        </p>
        <button
          onClick={load}
          className="flex items-center gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary font-headline px-4 py-2 rounded-lg text-xs font-bold"
        >
          <RotateCw className="h-3.5 w-3.5" />
          Thử lại
        </button>
      </div>
    );
  }

  const { summary, health } = state;
  const { counts, recent_activity: recentActivity } = summary;
  const hasAnyData = counts.documents > 0 || counts.conversations > 0 || counts.scans > 0;
  const healthStatus = health?.status ?? 'unknown';

  return (
    <div className="space-y-6">

      {/* Page Header */}
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">CyberSec Assistant</h2>
          <p className="text-xs text-text-secondary">Kiểm tra và hỗ trợ an toàn thông tin — số liệu và hoạt động gần đây từ tài khoản của bạn.</p>
        </div>
        <div className="text-right text-[10px] font-mono text-text-muted">
          <span>TRẠNG THÁI HỆ THỐNG</span>
          <span
            className={`block font-bold uppercase ${
              healthStatus === 'healthy' ? 'text-primary' : healthStatus === 'unknown' ? 'text-text-muted' : 'text-critical'
            }`}
          >
            {healthStatus}
          </span>
        </div>
      </div>

      {/* Metrics Cards Grid - every number here is a real COUNT(*) scoped to this account. */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">

        <div
          className="bg-surface-container border border-surface-container-highest rounded-xl p-5 hover:border-primary/20 transition-all cursor-pointer group"
          onClick={() => navigate('/knowledge-base')}
        >
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Tài liệu Knowledge Base</span>
              <h3 className="font-headline font-black text-3xl mt-1 text-text-primary">{counts.documents}</h3>
            </div>
            <div className="p-2 bg-info/10 rounded-lg text-info border border-info/10">
              <FileText className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <span className="text-[10px] font-mono text-info font-bold uppercase">Mở Knowledge Base</span>
            <ChevronRight className="h-4 w-4 text-text-muted group-hover:text-primary transition-colors" />
          </div>
        </div>

        <div
          className="bg-surface-container border border-surface-container-highest rounded-xl p-5 hover:border-primary/20 transition-all cursor-pointer group"
          onClick={() => navigate('/ai')}
        >
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Cuộc trò chuyện AI</span>
              <h3 className="font-headline font-black text-3xl mt-1 text-text-primary">{counts.conversations}</h3>
            </div>
            <div className="p-2 bg-primary/10 rounded-lg text-primary border border-primary/10">
              <MessageSquare className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <span className="text-[10px] font-mono text-primary font-bold uppercase">{counts.messages} tin nhắn</span>
            <ChevronRight className="h-4 w-4 text-text-muted group-hover:text-primary transition-colors" />
          </div>
        </div>

        <div
          className="bg-surface-container border border-surface-container-highest rounded-xl p-5 hover:border-primary/20 transition-all cursor-pointer group"
          onClick={() => navigate('/toolkit/history')}
        >
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Lượt quét bảo mật</span>
              <h3 className="font-headline font-black text-3xl mt-1 text-text-primary">{counts.scans}</h3>
            </div>
            <div className="p-2 bg-critical/10 rounded-lg text-critical border border-critical/10">
              <Search className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <span className="text-[10px] font-mono text-critical font-bold uppercase">URL / CVE / Mật khẩu</span>
            <ChevronRight className="h-4 w-4 text-text-muted group-hover:text-primary transition-colors" />
          </div>
        </div>

        <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5">
          <div className="flex justify-between items-start">
            <div>
              <span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Kiểm tra phụ thuộc</span>
              <h3 className="font-headline font-black text-3xl mt-1 text-text-primary">
                {health ? Object.values(health.checks).filter((c) => c.status === 'healthy').length : '—'}
                <span className="text-sm text-text-muted">/{health ? Object.values(health.checks).length : '—'}</span>
              </h3>
            </div>
            <div className="p-2 bg-low/10 rounded-lg text-low border border-low/10">
              <ShieldCheck className="h-5 w-5" />
            </div>
          </div>
          <div className="mt-4 flex items-center justify-between">
            <span className="text-[10px] font-mono text-low font-bold uppercase">
              {health ? 'ổn định' : 'không thể kết nối'}
            </span>
          </div>
        </div>

      </div>

      {/* Recent Activity - real rows from conversations / documents / scan history, merged and sorted. */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-surface-container border border-surface-container-highest rounded-xl p-5 flex flex-col">
          <div className="flex justify-between items-center mb-4">
            <div>
              <h3 className="font-headline font-bold text-sm text-text-primary">Hoạt động gần đây</h3>
              <p className="text-[10px] text-text-muted font-mono uppercase">Tài liệu, cuộc trò chuyện và lượt quét gần đây nhất của bạn</p>
            </div>
          </div>

          {recentActivity.length === 0 ? (
            <div className="flex-1 flex flex-col items-center justify-center gap-2 py-10 text-center">
              <p className="text-xs text-text-secondary">Chưa có hoạt động nào.</p>
              <p className="text-[10px] text-text-muted">
                Tải lên tài liệu, bắt đầu cuộc trò chuyện AI, hoặc chạy quét bảo mật để xem hoạt động tại đây.
              </p>
            </div>
          ) : (
            <>
            <div className="md:hidden space-y-3">
              {recentActivity.map((item) => (
                <button
                  key={`${item.type}-${item.id}`}
                  type="button"
                  className="w-full rounded-lg border border-surface-container-highest bg-surface-container-high/30 px-3 py-3 text-left"
                  onClick={() => navigate(item.href)}
                >
                  <span className="block text-[10px] font-mono uppercase text-text-muted">
                    {ACTIVITY_LABEL[item.type] ?? item.type}
                  </span>
                  <span className="mt-1 block truncate text-xs font-mono font-bold text-text-primary" title={item.title}>
                    {item.title}
                  </span>
                  <span className="mt-2 flex items-center justify-between gap-3 text-[10px] font-mono text-text-muted">
                    <span className="truncate capitalize">{item.detail ?? '—'}</span>
                    <span className="shrink-0 text-right">{formatRelativeTime(item.created_at)}</span>
                  </span>
                </button>
              ))}
            </div>
            <div
              className="hidden md:block overflow-x-auto flex-1"
              tabIndex={0}
              aria-label="Recent activity table"
            >
              <table className="w-full min-w-[620px] table-fixed text-left text-xs font-mono">
                <colgroup>
                  <col className="w-[38%]" />
                  <col className="w-[36%]" />
                  <col className="w-[12%]" />
                  <col className="w-[14%]" />
                </colgroup>
                <thead>
                  <tr className="border-b border-surface-container-highest text-text-muted text-[10px] uppercase">
                    <th className="py-2.5">Loại</th>
                    <th className="py-2.5">Tiêu đề</th>
                    <th className="py-2.5">Chi tiết</th>
                    <th className="py-2.5">Thời gian</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-surface-container-highest/40 text-text-secondary">
                  {recentActivity.map((item) => (
                    <tr
                      key={`${item.type}-${item.id}`}
                      className="hover:bg-surface-container-high/40 transition-colors cursor-pointer"
                      onClick={() => navigate(item.href)}
                    >
                      <td className="py-3 pr-4 text-text-primary font-bold">
                        <span className="block truncate">{ACTIVITY_LABEL[item.type] ?? item.type}</span>
                      </td>
                      <td className="py-3 pr-4" title={item.title}>
                        <span className="block truncate">{item.title}</span>
                      </td>
                      <td className="py-3 text-[10px] capitalize text-text-muted">{item.detail ?? '—'}</td>
                      <td className="py-3 text-[10px] text-text-muted">
                        <span className="block whitespace-normal leading-snug">{formatRelativeTime(item.created_at)}</span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            </>
          )}
        </div>

        {/* Quick actions to real, working tools. */}
        <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5 flex flex-col">
          <div className="mb-4">
            <h3 className="font-headline font-bold text-sm text-text-primary">Thao tác nhanh</h3>
            <p className="text-[10px] text-text-muted font-mono uppercase">Truy cập nhanh công cụ</p>
          </div>
          <div className="flex-1 space-y-2">
            <button
              onClick={() => navigate('/toolkit/url-scanner')}
              className="w-full flex items-center justify-between gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary font-headline px-3 py-2.5 rounded-lg transition-all text-[11px] font-bold"
            >
              <span>Kiểm tra Website</span>
              <ArrowUpRight className="h-3.5 w-3.5 text-primary" />
            </button>
            <button
              onClick={() => navigate('/toolkit/password-checker')}
              className="w-full flex items-center justify-between gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary font-headline px-3 py-2.5 rounded-lg transition-all text-[11px] font-bold"
            >
              <span>Kiểm tra Mật khẩu</span>
              <ArrowUpRight className="h-3.5 w-3.5 text-primary" />
            </button>
            <button
              onClick={() => navigate('/toolkit/cve-lookup')}
              className="w-full flex items-center justify-between gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary font-headline px-3 py-2.5 rounded-lg transition-all text-[11px] font-bold"
            >
              <span>Tra cứu CVE</span>
              <ArrowUpRight className="h-3.5 w-3.5 text-primary" />
            </button>
            <button
              onClick={() => navigate('/ai')}
              className="w-full flex items-center justify-between gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary font-headline px-3 py-2.5 rounded-lg transition-all text-[11px] font-bold"
            >
              <span>Hỏi AI</span>
              <ArrowUpRight className="h-3.5 w-3.5 text-primary" />
            </button>
          </div>
          {!hasAnyData && (
            <p className="mt-4 text-[10px] text-text-muted leading-relaxed">
              This account has no data yet - the counts above are real, not placeholders; they will
              update the moment you use a tool.
            </p>
          )}
        </div>
      </div>

    </div>
  );
};
