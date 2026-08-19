import { apiGet, apiPatch, apiPost } from './client';
import type { Page } from './chatbot';

export type FindingSeverity = 'low' | 'medium' | 'high' | 'critical';
export type FindingStatus =
  | 'open'
  | 'confirmed'
  | 'in_progress'
  | 'fixed'
  | 'verified'
  | 'closed'
  | 'false_positive'
  | 'accepted_risk'
  | 'reopened';

export interface Finding {
  id: string;
  project_id: string;
  scan_run_id: string | null;
  fingerprint: string;
  rule_id: string;
  category: string;
  title: string;
  evidence: string;
  impact: string;
  remediation: string;
  severity: FindingSeverity;
  status: FindingStatus;
  target: string;
  cve_id: string | null;
  assignee_user_id: string | null;
  deadline: string | null;
  /** Computed at read time (backend.services.sla.is_overdue) - never a
   * stored column. */
  is_overdue: boolean;
  verification_notes: string;
  resolution_reason: string | null;
  first_seen_scan_run_id: string | null;
  last_seen_scan_run_id: string | null;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface FindingTransition {
  id: string;
  finding_id: string;
  from_status: string;
  to_status: string;
  actor_user_id: string;
  reason: string | null;
  created_at: string;
}

export interface FindingCreateInput {
  rule_id: string;
  category: string;
  title: string;
  evidence?: string;
  impact?: string;
  remediation?: string;
  severity: FindingSeverity;
  target: string;
  cve_id?: string | null;
  assignee_user_id?: string | null;
}

export interface FindingFilters {
  page?: number;
  pageSize?: number;
  status?: FindingStatus;
  severity?: FindingSeverity;
  assigneeUserId?: string;
  overdue?: boolean;
}

/** A project member eligible to be a Finding's assignee (Task 4) - project
 * role developer/security/owner, never viewer. No local User table exists
 * in this app, so (same as ProjectMember) there is no display name/email -
 * just the raw user_id. */
export interface EligibleAssignee {
  user_id: string;
  project_role: 'developer' | 'security' | 'owner';
}

/** A cross-project "My Tasks" row: a Finding plus its parent project's name. */
export interface MyTask extends Finding {
  project_name: string;
}

export interface MyTaskFilters {
  page?: number;
  pageSize?: number;
  status?: FindingStatus;
  severity?: FindingSeverity;
  overdue?: boolean;
}

export function listFindings(projectId: string, filters: FindingFilters = {}): Promise<Page<Finding>> {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 20));
  if (filters.status) params.set('status', filters.status);
  if (filters.severity) params.set('severity', filters.severity);
  if (filters.assigneeUserId) params.set('assignee_user_id', filters.assigneeUserId);
  if (filters.overdue !== undefined) params.set('overdue', String(filters.overdue));
  return apiGet<Page<Finding>>(`/api/projects/${projectId}/findings?${params.toString()}`);
}

export function getFinding(projectId: string, findingId: string): Promise<Finding> {
  return apiGet<Finding>(`/api/projects/${projectId}/findings/${findingId}`);
}

export function createFinding(projectId: string, input: FindingCreateInput): Promise<Finding> {
  return apiPost<Finding>(`/api/projects/${projectId}/findings`, input);
}

export function transitionFinding(
  projectId: string,
  findingId: string,
  toStatus: FindingStatus,
  reason?: string,
): Promise<Finding> {
  return apiPost<Finding>(`/api/projects/${projectId}/findings/${findingId}/transition`, {
    to_status: toStatus,
    reason: reason ?? null,
  });
}

export function setAssignee(
  projectId: string,
  findingId: string,
  assigneeUserId: string | null,
): Promise<Finding> {
  return apiPatch<Finding>(`/api/projects/${projectId}/findings/${findingId}/assignee`, {
    assignee_user_id: assigneeUserId,
  });
}

export function listEligibleAssignees(projectId: string): Promise<{ items: EligibleAssignee[] }> {
  return apiGet<{ items: EligibleAssignee[] }>(`/api/projects/${projectId}/findings/eligible-assignees`);
}

export function listMyTasks(filters: MyTaskFilters = {}): Promise<Page<MyTask>> {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 20));
  if (filters.status) params.set('status', filters.status);
  if (filters.severity) params.set('severity', filters.severity);
  if (filters.overdue !== undefined) params.set('overdue', String(filters.overdue));
  return apiGet<Page<MyTask>>(`/api/findings/my-tasks?${params.toString()}`);
}
