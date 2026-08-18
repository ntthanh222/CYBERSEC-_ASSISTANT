import React, { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { AlertTriangle, Download, FileSpreadsheet, LogOut, Play, RefreshCw, Trash2 } from 'lucide-react';
import {
  downloadReportContent,
  listReports,
  type ReportCategory,
  type ReportRecord,
} from '../../../lib/api/reports';
import { getDemoStatus, resetDemoMode, startDemoMode, type DemoChain } from '../../../lib/api/demo';

export const ReportsCenterView: React.FC = () => {
  const [tab, setTab] = useState<'reports' | 'demo'>('reports');
  const [items, setItems] = useState<ReportRecord[]>([]);
  const [category, setCategory] = useState<ReportCategory | 'all'>('all');
  const [downloadPreview, setDownloadPreview] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);
  const [demo, setDemo] = useState<DemoChain | null>(null);
  const [isDemoLoading, setIsDemoLoading] = useState(false);
  const [demoNotice, setDemoNotice] = useState('');

  const load = useCallback(() => {
    setIsLoading(true);
    setError('');
    listReports(category === 'all' ? undefined : category)
      .then((page) => setItems(page.items))
      .catch((err) =>
        setError(err instanceof Error ? err.message : 'Không thể tải danh sách báo cáo.'),
      )
      .finally(() => setIsLoading(false));
  }, [category]);

  useEffect(load, [load]);
  useEffect(() => {
    getDemoStatus().then(setDemo).catch(() => undefined);
  }, []);

  const download = async (report: ReportRecord) => {
    setDownloadPreview(await downloadReportContent(report.id));
  };

  const startDemo = async () => {
    setIsDemoLoading(true);
    setError('');
    setDemoNotice('');
    try {
      setDemo(await startDemoMode());
      setDemoNotice('Demo Mode is ready. Demo data stays inside the demo_superadmin scope.');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Không thể bắt đầu Demo Mode.');
    } finally {
      setIsDemoLoading(false);
    }
  };

  const resetDemo = async () => {
    setIsDemoLoading(true);
    setError('');
    setDemoNotice('');
    try {
      const result = await resetDemoMode();
      setDemo(result);
      const deletedTotal = Object.values(result.deleted).reduce((sum, value) => sum + value, 0);
      setDemoNotice(`Reset Demo removed ${deletedTotal} demo records. Operational data was not touched.`);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not reset Demo Mode.');
    } finally {
      setIsDemoLoading(false);
    }
  };

  const exitDemo = () => {
    setTab('reports');
    setDemoNotice('Exited Demo Mode screen. Demo data is still available for the next rehearsal.');
  };

  return (
    <div className="space-y-6">
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Reports & Demo</h2>
          <p className="text-xs text-text-secondary">Báo cáo tải xuống thật và kịch bản demo liên kết dữ liệu bảo mật.</p>
        </div>
        <div className="flex gap-2">
          <Link to="/reports/builder" className="bg-primary text-background rounded px-3 py-2 text-xs font-bold">Tạo báo cáo</Link>
          <button onClick={load} className="flex items-center gap-1.5 px-3 py-2 rounded-lg border border-surface-container-highest text-xs"><RefreshCw className="h-3.5 w-3.5" /> Làm mới</button>
        </div>
      </div>

      <div className="border-b border-surface-container-highest flex items-center gap-1 overflow-x-auto">
        <button onClick={() => setTab('reports')} className={`px-4 py-2.5 text-xs font-bold border-b-2 ${tab === 'reports' ? 'border-primary text-primary bg-primary/5' : 'border-transparent text-text-secondary'}`}>Báo cáo</button>
        <button onClick={() => setTab('demo')} className={`px-4 py-2.5 text-xs font-bold border-b-2 ${tab === 'demo' ? 'border-primary text-primary bg-primary/5' : 'border-transparent text-text-secondary'}`}>Demo Mode</button>
      </div>

      {error && <div className="flex items-center gap-2 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical"><AlertTriangle className="h-4 w-4" />{error}</div>}
      {demoNotice && <div className="rounded-lg border border-success/30 bg-success/10 p-3 text-xs text-success">{demoNotice}</div>}

      {tab === 'demo' && (
        <section className="space-y-4 bg-surface-container border border-surface-container-highest rounded-lg p-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="font-headline font-bold text-sm text-text-primary">DEMO MODE</h3>
              <p className="text-xs text-text-secondary">Chuỗi demo CVE → Asset → Alert → Incident → Playbook → MITRE → Attack Graph → Report được seed riêng cho tài khoản demo_superadmin.</p>
            </div>
            <div className="flex flex-wrap justify-end gap-2">
              <button onClick={exitDemo} className="flex items-center gap-2 border border-surface-container-highest rounded px-3 py-2 text-xs font-bold text-text-secondary">
                <LogOut className="h-3.5 w-3.5" />
                Exit Demo
              </button>
              <button onClick={resetDemo} disabled={isDemoLoading || !demo?.active} className="flex items-center gap-2 border border-critical/40 text-critical rounded px-3 py-2 text-xs font-bold disabled:opacity-50">
                <Trash2 className="h-3.5 w-3.5" />
                Reset Demo
              </button>
            <button onClick={startDemo} disabled={isDemoLoading} className="flex items-center gap-2 bg-primary text-background rounded px-3 py-2 text-xs font-bold disabled:opacity-50">
              <Play className="h-3.5 w-3.5" />
              {isDemoLoading ? 'Đang chuẩn bị...' : 'Start Log4Shell demo'}
            </button>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            <div className="bg-background border border-surface-container-highest rounded p-3">Asset: {demo?.asset?.name ?? 'Chưa sẵn sàng'}</div>
            <div className="bg-background border border-surface-container-highest rounded p-3">CVE: {demo?.vulnerability?.cve_id ?? 'Chưa sẵn sàng'}</div>
            <div className="bg-background border border-surface-container-highest rounded p-3">Incident: {demo?.incident?.title ?? 'Chưa sẵn sàng'}</div>
          </div>
          <div className="flex flex-wrap gap-2">
            {demo && Object.entries(demo.routes).map(([key, route]) => (
              <Link key={key} to={String(route)} className="border border-surface-container-highest rounded px-3 py-2 text-xs text-text-secondary hover:text-primary">{key.replace('_', ' ')}</Link>
            ))}
          </div>
          <p className="text-[10px] text-text-muted font-mono uppercase">Isolation: {demo?.isolation ?? 'not_started'}</p>
        </section>
      )}

      {tab === 'reports' && (
        <>
          <select value={category} onChange={(e) => setCategory(e.target.value as ReportCategory | 'all')} className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs">
            <option value="all">Tất cả danh mục</option>
            <option value="executive">Điều hành</option>
            <option value="technical">Kỹ thuật</option>
            <option value="compliance">Tuân thủ</option>
            <option value="incident">Sự cố</option>
          </select>

          {isLoading ? <div className="py-12 text-center text-xs text-text-muted">Đang tải báo cáo...</div> : items.length === 0 ? (
            <div className="py-12 text-center text-xs text-text-muted border border-dashed border-surface-container-highest rounded-lg">Chưa có báo cáo nào được tạo.</div>
          ) : (
            <div className="space-y-3">
              {items.map((report) => (
                <article key={report.id} className="bg-surface-container border border-surface-container-highest rounded-lg p-4" data-testid={`report-row-${report.id}`}>
                  <div className="flex items-start gap-3">
                    <FileSpreadsheet className="h-5 w-5 text-primary mt-1" />
                    <div className="flex-1 min-w-0">
                      <Link to={`/reports/history?report=${report.id}`} className="font-bold text-text-primary hover:text-primary">{report.title}</Link>
                      <p className="text-[10px] text-text-muted mt-1">{report.category} - {report.format} - {new Date(report.created_at).toLocaleString()}</p>
                      <p className="text-xs text-text-secondary mt-2">{report.sections.join(', ') || 'Không có mục nào được ghi nhận'}</p>
                    </div>
                    <button onClick={() => download(report)} className="flex items-center gap-1.5 px-3 py-2 rounded border border-surface-container-highest text-xs"><Download className="h-3.5 w-3.5" /> Tải xuống</button>
                  </div>
                </article>
              ))}
            </div>
          )}

          {downloadPreview && (
            <pre className="max-h-64 overflow-auto bg-background border border-surface-container-highest rounded-lg p-3 text-xs whitespace-pre-wrap" data-testid="report-download-preview">{downloadPreview}</pre>
          )}
        </>
      )}
    </div>
  );
};

export default ReportsCenterView;
