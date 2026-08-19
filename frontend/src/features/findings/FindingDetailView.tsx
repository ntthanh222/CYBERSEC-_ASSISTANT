import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import {
  getFinding,
  transitionFinding,
  type Finding,
  type FindingStatus,
} from '../../lib/api/findings';
import { listProjectMembers, type ProjectRole } from '../../lib/api/projects';
import { ApiError } from '../../lib/api/client';
import { useAuth } from '../auth/AuthContext';
import { AlertTriangle, ArrowLeft, RefreshCw } from 'lucide-react';

//: Client-side convenience mirror of backend.services.finding_state_machine
//: - the backend is the real authorization gate; this only decides which
//: buttons to render so a user isn't offered an action the server would
//: reject. Never treat this table as authoritative.
const ALLOWED_TRANSITIONS: Record<FindingStatus, FindingStatus[]> = {
  open: ['confirmed', 'false_positive', 'accepted_risk'],
  confirmed: ['in_progress', 'false_positive', 'accepted_risk'],
  in_progress: ['fixed', 'false_positive', 'accepted_risk'],
  fixed: ['verified', 'reopened'],
  verified: ['closed', 'reopened'],
  closed: ['reopened'],
  false_positive: ['reopened'],
  accepted_risk: ['reopened'],
  reopened: ['confirmed', 'in_progress'],
};

const OWNER_SECURITY_ONLY_EDGES = new Set([
  'open->confirmed',
  'open->false_positive',
  'open->accepted_risk',
  'confirmed->in_progress',
  'confirmed->false_positive',
  'confirmed->accepted_risk',
  'fixed->verified',
  'verified->closed',
  'reopened->confirmed',
  'reopened->in_progress',
  'closed->reopened',
  'false_positive->reopened',
  'accepted_risk->reopened',
]);

const REASON_REQUIRED = new Set(['false_positive', 'accepted_risk']);

function isTransitionAllowedForActor(
  from: FindingStatus,
  to: FindingStatus,
  role: ProjectRole | null,
  globalRole: string | undefined,
  isAssignee: boolean,
): boolean {
  if (globalRole === 'admin' || globalRole === 'super_admin') return true;
  if (role === 'owner' || role === 'security') return true;
  const edge = `${from}->${to}`;
  if (!OWNER_SECURITY_ONLY_EDGES.has(edge) && role === 'developer' && isAssignee) return true;
  return false;
}

export const FindingDetailView: React.FC = () => {
  const { id, findingId } = useParams<{ id: string; findingId: string }>();
  const { user } = useAuth();

  const [finding, setFinding] = useState<Finding | null>(null);
  const [myRole, setMyRole] = useState<ProjectRole | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [reasonDraft, setReasonDraft] = useState('');
  const [pendingTransition, setPendingTransition] = useState<FindingStatus | null>(null);

  const load = useCallback(() => {
    if (!id || !findingId) return;
    setIsLoading(true);
    Promise.all([getFinding(id, findingId), listProjectMembers(id)])
      .then(([findingRecord, memberPage]) => {
        setFinding(findingRecord);
        const mine = memberPage.items.find((member) => member.user_id === user?.id);
        setMyRole(mine?.project_role ?? null);
        setErrorMsg(null);
      })
      .catch((err) => setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải phát hiện.'))
      .finally(() => setIsLoading(false));
  }, [id, findingId, user?.id]);

  useEffect(() => {
    load();
  }, [load]);

  const isAssignee = !!finding && !!user && finding.assignee_user_id === user.id;

  const availableTransitions = useMemo(() => {
    if (!finding) return [];
    return ALLOWED_TRANSITIONS[finding.status].filter((to) =>
      isTransitionAllowedForActor(finding.status, to, myRole, user?.role, isAssignee),
    );
  }, [finding, myRole, user?.role, isAssignee]);

  const handleTransition = async (to: FindingStatus) => {
    if (!id || !findingId || !finding) return;
    if (REASON_REQUIRED.has(to) && pendingTransition !== to) {
      setPendingTransition(to);
      return;
    }
    setActionError(null);
    try {
      const reason = REASON_REQUIRED.has(to) ? reasonDraft : undefined;
      const updated = await transitionFinding(id, findingId, to, reason);
      setFinding(updated);
      setPendingTransition(null);
      setReasonDraft('');
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : 'Không thể chuyển trạng thái.');
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-20 text-text-muted" data-testid="finding-detail-loading">
        <RefreshCw className="h-8 w-8 animate-spin text-primary" />
      </div>
    );
  }

  if (errorMsg || !finding) {
    return (
      <div className="flex flex-col items-center justify-center py-20 gap-3 text-text-muted" data-testid="finding-detail-error">
        <AlertTriangle className="h-10 w-10 text-critical" />
        <p className="text-xs text-text-secondary">{errorMsg ?? 'Không tìm thấy phát hiện.'}</p>
      </div>
    );
  }

  return (
    <div className="space-y-6" data-testid="finding-detail-view">
      <Link to={`/projects/${id}`} className="inline-flex items-center gap-1.5 text-xs text-text-secondary hover:text-text-primary">
        <ArrowLeft className="h-3.5 w-3.5" />
        Quay lại dự án
      </Link>

      <div className="border-b border-surface-container-highest/60 pb-4">
        <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">{finding.title}</h2>
        <p className="text-xs text-text-secondary mt-1">
          {finding.severity.toUpperCase()} · {finding.status} · {finding.target}
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Field label="Bằng chứng" value={finding.evidence || '—'} />
        <Field label="Tác động" value={finding.impact || '—'} />
        <Field label="Biện pháp khắc phục" value={finding.remediation || '—'} />
      </div>

      {finding.resolution_reason && (
        <Field label="Lý do giải quyết" value={finding.resolution_reason} />
      )}

      <div className="space-y-3" data-testid="finding-transitions">
        {actionError && <p className="text-xs text-critical">{actionError}</p>}
        {availableTransitions.length === 0 ? (
          <p className="text-xs text-text-muted italic">Không có hành động chuyển trạng thái nào khả dụng cho bạn.</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {availableTransitions.map((to) => (
              <button
                key={to}
                onClick={() => handleTransition(to)}
                data-testid={`transition-${to}`}
                className="px-3 py-2 border border-surface-container-highest rounded-lg text-xs font-mono font-bold text-text-secondary hover:text-text-primary hover:border-primary"
              >
                {to.toUpperCase()}
              </button>
            ))}
          </div>
        )}
        {pendingTransition && REASON_REQUIRED.has(pendingTransition) && (
          <div className="flex flex-wrap gap-2 items-end">
            <div className="flex-1 min-w-[240px]">
              <label className="block text-[10px] font-mono uppercase tracking-widest text-text-muted mb-1">
                Lý do (bắt buộc)
              </label>
              <input
                type="text"
                value={reasonDraft}
                onChange={(event) => setReasonDraft(event.target.value)}
                className="w-full bg-background border border-surface-container-highest rounded-lg px-3 py-2 text-xs text-text-primary focus:outline-none"
              />
            </div>
            <button
              onClick={() => handleTransition(pendingTransition)}
              disabled={!reasonDraft.trim()}
              className="px-3 py-2 bg-primary text-background rounded-lg text-xs font-mono font-bold disabled:opacity-40"
            >
              XÁC NHẬN
            </button>
          </div>
        )}
      </div>
    </div>
  );
};

const Field: React.FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="bg-surface-container border border-surface-container-highest rounded-xl p-3 space-y-1">
    <span className="text-[9px] font-mono uppercase tracking-widest text-text-muted font-bold">{label}</span>
    <p className="text-xs text-text-primary whitespace-pre-wrap">{value}</p>
  </div>
);

export default FindingDetailView;
