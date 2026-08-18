import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { getAdminSummary, getCrawlerStatus, runCrawlerNow } from '../../../lib/api/admin';
import type { AdminCrawlerStatus, AdminSummary } from '../../../lib/api/admin';
import { getAiHealth, getSystemHealth } from '../../../lib/api/system';
import type { AiHealthResponse, SystemHealthResponse } from '../../../lib/api/system';
import { createSecurityNews } from '../../../lib/api/securityNews';
import { ApiError } from '../../../lib/api/client';
import { AdminConsoleNav } from '../components/AdminConsoleNav';
import { Bot, Database, FileText, HeartPulse, Lock, PlusCircle, RotateCw, Search, ShieldCheck, Users } from 'lucide-react';

type LoadState =
  | { status: 'loading' }
  | { status: 'error'; message: string }
  | { status: 'ready'; summary: AdminSummary };

type AsyncState<T> =
  | { status: 'loading' }
  | { status: 'error'; message?: string }
  | { status: 'ready'; data: T };

const statusClass = (status: string) => {
  if (status === 'healthy' || status === 'ready') return 'text-primary';
  if (status === 'degraded' || status === 'warming') return 'text-warning';
  return 'text-critical';
};

export const AdminOverviewView: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const [state, setState] = useState<LoadState>({ status: 'loading' });
  const [aiHealthState, setAiHealthState] = useState<AsyncState<AiHealthResponse>>({ status: 'loading' });
  const [healthState, setHealthState] = useState<AsyncState<SystemHealthResponse>>({ status: 'loading' });
  const [crawler, setCrawler] = useState<AdminCrawlerStatus | null>(null);
  const [crawlerError, setCrawlerError] = useState('');
  const [isCrawlerRunning, setIsCrawlerRunning] = useState(false);
  const [manualForm, setManualForm] = useState({ title: '', url: '', source: '', summary: '' });
  const [manualError, setManualError] = useState('');
  const [manualSuccess, setManualSuccess] = useState(false);
  const [isSavingManual, setIsSavingManual] = useState(false);

  const activeTab = useMemo(() => {
    if (location.pathname.includes('/crawler')) return 'crawler';
    if (location.pathname.includes('/rag')) return 'rag';
    if (location.pathname.includes('/health')) return 'health';
    if (location.pathname.includes('/settings')) return 'settings';
    return 'overview';
  }, [location.pathname]);

  const load = useCallback(async () => {
    setState({ status: 'loading' });
    try {
      const summary = await getAdminSummary();
      setState({ status: 'ready', summary });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : 'Cannot connect to backend.';
      setState({ status: 'error', message });
    }
  }, []);

  const loadAuxiliary = useCallback(async () => {
    setAiHealthState({ status: 'loading' });
    setHealthState({ status: 'loading' });
    setCrawlerError('');
    try {
      setAiHealthState({ status: 'ready', data: await getAiHealth() });
    } catch (err) {
      setAiHealthState({ status: 'error', message: err instanceof Error ? err.message : undefined });
    }
    try {
      setHealthState({ status: 'ready', data: await getSystemHealth() });
    } catch (err) {
      setHealthState({ status: 'error', message: err instanceof Error ? err.message : undefined });
    }
    try {
      setCrawler(await getCrawlerStatus());
    } catch {
      setCrawlerError('Cannot load crawler status.');
    }
  }, []);

  useEffect(() => {
    load();
    loadAuxiliary();
  }, [load, loadAuxiliary]);

  const runCrawler = async () => {
    setIsCrawlerRunning(true);
    setCrawlerError('');
    try {
      setCrawler(await runCrawlerNow());
    } catch (err) {
      setCrawlerError(err instanceof Error ? err.message : 'Cannot run crawler.');
    } finally {
      setIsCrawlerRunning(false);
    }
  };

  const handleManualSubmit = async (event: React.FormEvent) => {
    event.preventDefault();
    setManualError('');
    setManualSuccess(false);
    setIsSavingManual(true);
    try {
      await createSecurityNews({
        title: manualForm.title,
        url: manualForm.url,
        source: manualForm.source,
        summary: manualForm.summary,
        published_at: new Date().toISOString(),
      });
      setManualForm({ title: '', url: '', source: '', summary: '' });
      setManualSuccess(true);
    } catch (err) {
      setManualError(err instanceof ApiError ? err.message : 'Không thể lưu bài viết.');
    } finally {
      setIsSavingManual(false);
    }
  };

  if (state.status === 'loading') {
    return <div className="p-4 text-xs text-text-muted font-mono">Loading Control Console...</div>;
  }

  if (state.status === 'error') {
    return (
      <div className="flex flex-col items-center justify-center gap-4 py-24 text-center">
        <p className="text-sm text-text-secondary">Cannot load Control Console: {state.message}</p>
        <button onClick={load} className="flex items-center gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary px-4 py-2 rounded-lg text-xs font-bold">
          <RotateCw className="h-3.5 w-3.5" /> Retry
        </button>
      </div>
    );
  }

  const { summary } = state;
  const aiReady = aiHealthState.status === 'ready' ? aiHealthState.data : null;
  const healthReady = healthState.status === 'ready' ? healthState.data : null;

  return (
    <div className="space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3 border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">Control Console</h2>
          <p className="text-xs text-text-secondary">Professional administration over users, audit, AI readiness, crawler, and safe runtime status.</p>
        </div>
        <div className="text-left sm:text-right text-[10px] font-mono text-text-muted">
          <span>SYSTEM STATUS</span>
          <span className={`block font-bold uppercase ${statusClass(summary.system_status)}`}>{summary.system_status}</span>
        </div>
      </div>

      <AdminConsoleNav />

      {activeTab === 'overview' && (
        <>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
            <button onClick={() => navigate('/admin/users')} className="text-left bg-surface-container border border-surface-container-highest rounded-lg p-5 hover:border-primary/30">
              <div className="flex justify-between items-start">
                <div><span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Users</span><h3 className="font-headline font-black text-3xl mt-1 text-text-primary">{summary.users.total}</h3></div>
                <Users className="h-5 w-5 text-primary" />
              </div>
              <div className="mt-4 text-[10px] font-mono text-text-muted uppercase">{summary.users.active} active · {summary.users.disabled} disabled · {summary.users.admins} admin tier</div>
            </button>
            <button onClick={() => navigate('/admin/audit')} className="text-left bg-surface-container border border-surface-container-highest rounded-lg p-5 hover:border-primary/30">
              <div className="flex justify-between items-start">
                <div><span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Security</span><h3 className="font-headline font-black text-3xl mt-1 text-text-primary">{summary.audit_events}</h3></div>
                <ShieldCheck className="h-5 w-5 text-info" />
              </div>
              <div className="mt-4 text-[10px] font-mono text-text-muted uppercase">{summary.recent_admin_actions} admin events in 24h</div>
            </button>
            <button onClick={() => navigate('/admin/rag')} className="text-left bg-surface-container border border-surface-container-highest rounded-lg p-5 hover:border-primary/30">
              <div className="flex justify-between items-start">
                <div><span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">AI / RAG</span><h3 className="font-headline font-black text-3xl mt-1 text-text-primary">{summary.content.documents}</h3></div>
                <Bot className="h-5 w-5 text-primary" />
              </div>
              <div className="mt-4 text-[10px] font-mono text-text-muted uppercase">{aiReady ? aiReady.provider : 'checking'} · {summary.content.conversations} conversations</div>
            </button>
            <button onClick={() => navigate('/admin/health')} className="text-left bg-surface-container border border-surface-container-highest rounded-lg p-5 hover:border-primary/30">
              <div className="flex justify-between items-start">
                <div><span className="text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">System</span><h3 className={`font-headline font-black text-3xl mt-1 uppercase ${statusClass(summary.system_status)}`}>{summary.system_status}</h3></div>
                <HeartPulse className="h-5 w-5 text-warning" />
              </div>
              <div className="mt-4 text-[10px] font-mono text-text-muted uppercase">DB · Redis · pgvector · auth secret</div>
            </button>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
            <section className="bg-surface-container border border-surface-container-highest rounded-lg p-5">
              <h3 className="font-headline font-bold text-sm text-text-primary">Role distribution</h3>
              <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                <div>User: <span className="font-bold text-text-primary">{summary.users.users}</span></div>
                <div>Analyst: <span className="font-bold text-text-primary">{summary.users.security_analysts}</span></div>
                <div>Admin: <span className="font-bold text-text-primary">{summary.users.admins - summary.users.super_admins}</span></div>
                <div>Super admin: <span className="font-bold text-text-primary">{summary.users.super_admins}</span></div>
              </div>
            </section>
            <section className="bg-surface-container border border-surface-container-highest rounded-lg p-5">
              <h3 className="font-headline font-bold text-sm text-text-primary">Data sources</h3>
              <div className="mt-4 grid grid-cols-2 gap-3 text-xs">
                <div>Demo: <span className="font-bold text-text-primary">{summary.users.demo}</span></div>
                <div>Test: <span className="font-bold text-text-primary">{summary.users.test}</span></div>
                <div>Local: <span className="font-bold text-text-primary">{summary.users.local}</span></div>
                <div>Hosted: <span className="font-bold text-text-primary">{summary.users.hosted}</span></div>
              </div>
            </section>
          </div>
        </>
      )}

      {activeTab === 'health' && (
        <section className="bg-surface-container border border-surface-container-highest rounded-lg p-5 space-y-4">
          <div className="flex items-center justify-between gap-3">
            <div><h3 className="font-headline font-bold text-sm text-text-primary">System Health</h3><p className="text-[10px] text-text-muted font-mono uppercase">Live public readiness endpoint</p></div>
            <button onClick={loadAuxiliary} className="flex items-center gap-2 border border-surface-container-highest rounded px-3 py-2 text-xs"><RotateCw className="h-3.5 w-3.5" /> Refresh</button>
          </div>
          {healthState.status === 'loading' && <p className="text-xs text-text-muted">Checking services...</p>}
          {healthState.status === 'error' && <p className="text-xs text-critical">Health endpoint is unavailable.</p>}
          {healthReady && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {Object.entries(healthReady.checks).map(([name, check]) => (
                <div key={name} className="border border-surface-container-highest rounded-lg p-4">
                  <div className="text-[10px] uppercase font-mono text-text-muted">{name.replaceAll('_', ' ')}</div>
                  <div className={`font-black uppercase ${statusClass(check.status)}`}>{check.status}</div>
                  <div className="text-[10px] text-text-muted">{check.latency_ms == null ? 'latency n/a' : `${check.latency_ms} ms`}</div>
                </div>
              ))}
              <div className="border border-surface-container-highest rounded-lg p-4">
                <div className="text-[10px] uppercase font-mono text-text-muted">Embedding</div>
                <div className={`font-black uppercase ${statusClass(healthReady.embedding.status)}`}>{healthReady.embedding.status}</div>
                <div className="text-[10px] text-text-muted">{healthReady.embedding.elapsed_seconds ?? 0}s elapsed</div>
              </div>
            </div>
          )}
        </section>
      )}

      {activeTab === 'rag' && (
        <section className="bg-surface-container border border-surface-container-highest rounded-lg p-5 space-y-4">
          <h3 className="font-headline font-bold text-sm text-text-primary">AI & Knowledge</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="border border-surface-container-highest rounded-lg p-4"><div className="text-text-muted uppercase text-[10px]">Provider</div><div className="font-bold text-text-primary">{aiReady?.provider ?? 'unknown'}</div></div>
            <div className="border border-surface-container-highest rounded-lg p-4"><div className="text-text-muted uppercase text-[10px]">RAG ready</div><div className={`font-bold ${aiReady?.rag_ready ? 'text-primary' : 'text-warning'}`}>{aiReady?.rag_ready ? 'ready' : 'not ready'}</div></div>
            <div className="border border-surface-container-highest rounded-lg p-4"><div className="text-text-muted uppercase text-[10px]">Documents</div><div className="font-bold text-text-primary">{summary.content.documents}</div></div>
          </div>
          <p className="text-xs text-text-secondary">{aiReady?.detail ?? 'AI health check did not return details.'}</p>
          <Link to="/knowledge-base" className="inline-flex items-center gap-2 bg-primary text-background rounded px-3 py-2 text-xs font-bold"><Database className="h-3.5 w-3.5" /> Open knowledge base</Link>
        </section>
      )}

      {activeTab === 'crawler' && (
        <section className="space-y-4 bg-surface-container border border-surface-container-highest rounded-lg p-5">
          <div className="flex items-center justify-between gap-3">
            <div><h3 className="font-headline font-bold text-sm text-text-primary">Crawler</h3><p className="text-[10px] text-text-muted font-mono uppercase">Allowlisted security news sources</p></div>
            <button onClick={runCrawler} disabled={isCrawlerRunning} className="flex items-center gap-2 bg-primary text-background rounded px-3 py-2 text-xs font-bold disabled:opacity-50"><RotateCw className={`h-3.5 w-3.5 ${isCrawlerRunning ? 'animate-spin' : ''}`} /> Run Now</button>
          </div>
          {crawlerError && <div className="rounded border border-critical/30 bg-critical/10 p-3 text-xs text-critical">{crawlerError}</div>}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-xs">
            <div className="bg-background border border-surface-container-highest rounded-lg p-3">Last: {crawler?.last_run ? new Date(crawler.last_run).toLocaleString() : 'Never'}</div>
            <div className="bg-background border border-surface-container-highest rounded-lg p-3">Next: {crawler?.next_run ? new Date(crawler.next_run).toLocaleString() : 'Manual'}</div>
            <div className="bg-background border border-surface-container-highest rounded-lg p-3">Collected: {crawler?.articles_collected ?? 0}</div>
            <div className="bg-background border border-surface-container-highest rounded-lg p-3">Failures: {crawler?.failed_items ?? 0}</div>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left min-w-[720px]">
              <thead className="text-[10px] text-text-muted uppercase border-b border-surface-container-highest"><tr><th className="py-2">Source</th><th>Enabled</th><th>Last result</th><th>Collected</th><th>Error</th></tr></thead>
              <tbody>
                {(crawler?.sources ?? []).map((source) => (
                  <tr key={source.source} className="border-b border-surface-container-highest/40">
                    <td className="py-2 font-bold text-text-primary">{source.source}</td>
                    <td>{source.enabled ? 'Enabled' : 'Disabled'}</td>
                    <td>{source.last_result}</td>
                    <td>{source.articles_collected ?? 0}</td>
                    <td className="text-critical">{source.error ?? ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Manual news article - moved here from the user-facing News page.
              Only admin/super_admin reach this tab, and the backend enforces
              the same restriction on POST /api/news independently. */}
          <div className="pt-4 border-t border-surface-container-highest/40 space-y-3">
            <h3 className="font-headline font-bold text-sm text-text-primary flex items-center gap-2">
              <PlusCircle className="h-4 w-4 text-primary" /> Thêm bài viết thủ công
            </h3>
            <form onSubmit={handleManualSubmit} className="grid grid-cols-1 lg:grid-cols-6 gap-2">
              <input required value={manualForm.title} onChange={(e) => setManualForm({ ...manualForm, title: e.target.value })} placeholder="Tiêu đề bài viết" className="lg:col-span-2 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
              <input required type="url" value={manualForm.url} onChange={(e) => setManualForm({ ...manualForm, url: e.target.value })} placeholder="https://source.example/article" className="lg:col-span-2 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
              <input required value={manualForm.source} onChange={(e) => setManualForm({ ...manualForm, source: e.target.value })} placeholder="Nguồn" className="bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
              <button disabled={isSavingManual} className="bg-primary text-background rounded px-3 py-2 text-xs font-bold disabled:opacity-50">{isSavingManual ? 'Đang lưu...' : 'Lưu bài viết'}</button>
              <input required value={manualForm.summary} onChange={(e) => setManualForm({ ...manualForm, summary: e.target.value })} placeholder="Tóm tắt" className="lg:col-span-6 bg-background border border-surface-container-highest rounded px-3 py-2 text-xs" />
            </form>
            {manualError && <div className="rounded border border-critical/30 bg-critical/10 p-2 text-xs text-critical">{manualError}</div>}
            {manualSuccess && <div className="rounded border border-primary/30 bg-primary/10 p-2 text-xs text-primary">Đã lưu bài viết - hiển thị ngay trong Tin tức Bảo mật cho mọi người dùng.</div>}
          </div>
        </section>
      )}

      {activeTab === 'settings' && (
        <section className="bg-surface-container border border-surface-container-highest rounded-lg p-5 space-y-4">
          <h3 className="font-headline font-bold text-sm text-text-primary">Security Settings</h3>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-xs">
            <div className="border border-surface-container-highest rounded-lg p-4"><Lock className="h-4 w-4 text-primary mb-2" /><div className="font-bold text-text-primary">Secrets hidden</div><div className="text-text-muted">No API keys, tokens, or passwords are rendered.</div></div>
            <div className="border border-surface-container-highest rounded-lg p-4"><ShieldCheck className="h-4 w-4 text-primary mb-2" /><div className="font-bold text-text-primary">RBAC enforced</div><div className="text-text-muted">Admin APIs re-read role and active state per request.</div></div>
            <div className="border border-surface-container-highest rounded-lg p-4"><Search className="h-4 w-4 text-primary mb-2" /><div className="font-bold text-text-primary">Audited changes</div><div className="text-text-muted">Role and activation mutations write admin audit rows.</div></div>
          </div>
          <button disabled className="border border-surface-container-highest rounded px-3 py-2 text-xs text-text-muted cursor-not-allowed">Runtime secret editing disabled</button>
        </section>
      )}

      {activeTab === 'overview' && (
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
          <button onClick={() => navigate('/admin/users')} className="flex items-center justify-between gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary px-4 py-3 rounded-lg text-xs font-bold"><span>Manage users & roles</span><Users className="h-4 w-4 text-primary" /></button>
          <button onClick={() => navigate('/admin/audit')} className="flex items-center justify-between gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary px-4 py-3 rounded-lg text-xs font-bold"><span>Review audit logs</span><FileText className="h-4 w-4 text-primary" /></button>
        </div>
      )}
    </div>
  );
};
