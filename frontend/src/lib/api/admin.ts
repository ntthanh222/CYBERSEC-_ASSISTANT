import { apiGet, apiPatch, apiPost } from './client';
import type { AppRole } from './auth';

export interface AdminUserCounts {
  total: number;
  admins: number;
  active: number;
  disabled: number;
  users: number;
  security_analysts: number;
  super_admins: number;
  demo: number;
  test: number;
  local: number;
  hosted: number;
}

export interface AdminContentCounts {
  documents: number;
  conversations: number;
  messages: number;
  scans: number;
}

export type AdminProjectHealthBucket = 'healthy' | 'warning' | 'critical';

export interface AdminProjectHealthItem {
  bucket: AdminProjectHealthBucket;
  count: number;
}

export interface AdminSummary {
  users: AdminUserCounts;
  content: AdminContentCounts;
  system_status: string;
  audit_events: number;
  recent_admin_actions: number;
  // Task 7: vuln-lifecycle admin overview additions.
  active_workspaces: number;
  active_projects: number;
  open_findings: number;
  critical_findings: number;
  high_findings: number;
  overdue_findings: number;
  waiting_verify_findings: number;
  fixed_this_week_findings: number;
  project_health: AdminProjectHealthItem[];
}

export interface AdminUserItem {
  user_id: string;
  email: string | null;
  username: string | null;
  role: AppRole;
  is_active: boolean;
  source: 'demo' | 'test' | 'local' | 'hosted';
  is_test_account: boolean;
  created_at: string;
  updated_at: string;
  last_login_at: string | null;
}

export interface AdminUserPage {
  items: AdminUserItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminAuditItem {
  id: string;
  actor_user_id: string | null;
  action: string;
  target_user_id: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface AdminAuditPage {
  items: AdminAuditItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface AdminCrawlerSource {
  source: string;
  enabled: boolean;
  url?: string;
  last_result: string;
  articles_collected?: number;
  error?: string;
}

export interface AdminCrawlerStatus {
  status: string;
  last_run: string | null;
  next_run: string | null;
  articles_collected: number;
  failed_items: number;
  last_result: string;
  errors: string[];
  sources: AdminCrawlerSource[];
}

export function getAdminSummary(): Promise<AdminSummary> {
  return apiGet<AdminSummary>('/api/admin/summary');
}

export interface AdminUserFilters {
  page?: number;
  pageSize?: number;
  search?: string;
  role?: AppRole | 'all';
  status?: 'all' | 'active' | 'disabled';
  source?: 'all' | 'demo' | 'test' | 'local' | 'hosted';
  hideTestAccounts?: boolean;
}

export interface AdminAuditFilters {
  page?: number;
  pageSize?: number;
  search?: string;
  action?: string;
  actorUserId?: string;
  targetUserId?: string;
}

export function listAdminUsers(filters: AdminUserFilters = {}): Promise<AdminUserPage> {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 25));
  if (filters.search?.trim()) params.set('search', filters.search.trim());
  if (filters.role && filters.role !== 'all') params.set('role', filters.role);
  if (filters.status && filters.status !== 'all') params.set('status', filters.status);
  if (filters.source && filters.source !== 'all') params.set('source', filters.source);
  params.set('hide_test_accounts', String(filters.hideTestAccounts ?? true));
  return apiGet<AdminUserPage>(`/api/admin/users?${params.toString()}`);
}

export function changeUserRole(userId: string, role: AppRole): Promise<AdminUserItem> {
  return apiPatch(`/api/admin/users/${userId}/role`, { role }) as Promise<AdminUserItem>;
}

export function setUserActive(userId: string, isActive: boolean): Promise<AdminUserItem> {
  return apiPatch(`/api/admin/users/${userId}/active`, { is_active: isActive }) as Promise<AdminUserItem>;
}

export function getAdminAuditLog(filters: AdminAuditFilters = {}): Promise<AdminAuditPage> {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 25));
  if (filters.search?.trim()) params.set('search', filters.search.trim());
  if (filters.action) params.set('action', filters.action);
  if (filters.actorUserId) params.set('actor_user_id', filters.actorUserId);
  if (filters.targetUserId) params.set('target_user_id', filters.targetUserId);
  return apiGet<AdminAuditPage>(`/api/admin/audit?${params.toString()}`);
}

export function getCrawlerStatus(): Promise<AdminCrawlerStatus> {
  return apiGet<AdminCrawlerStatus>('/api/admin/crawler');
}

export function runCrawlerNow(): Promise<AdminCrawlerStatus> {
  return apiPost<AdminCrawlerStatus>('/api/admin/crawler/run', {});
}
