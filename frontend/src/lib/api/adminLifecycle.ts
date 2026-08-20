import { apiGet, apiPost } from './client';
import type { Page } from './chatbot';
import type { Finding, FindingSeverity, FindingStatus } from './findings';
import type { Project, ProjectCriticality, ProjectEnvironment, ProjectStatus } from './projects';

/** Task 7: Admin Console visibility over Workspaces/Projects/Findings -
 * cross-project/cross-workspace, not membership-scoped. SLA policy
 * admin endpoints already exist in lib/api/slaPolicies.ts (Task 3). */

export interface AdminWorkspaceItem {
  id: string;
  name: string;
  description: string | null;
  created_by_user_id: string;
  member_count: number;
  project_count: number;
  created_at: string;
  updated_at: string;
}

export function listAdminWorkspaces(page = 1, pageSize = 20): Promise<Page<AdminWorkspaceItem>> {
  return apiGet<Page<AdminWorkspaceItem>>(`/api/admin/workspaces?page=${page}&page_size=${pageSize}`);
}

export interface AdminProjectItem extends Project {
  member_count: number;
  open_findings_count: number;
}

export interface AdminProjectFilters {
  page?: number;
  pageSize?: number;
  workspaceId?: string;
  environment?: ProjectEnvironment;
  criticality?: ProjectCriticality;
  status?: ProjectStatus;
}

export function listAdminProjects(filters: AdminProjectFilters = {}): Promise<Page<AdminProjectItem>> {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 20));
  if (filters.workspaceId) params.set('workspace_id', filters.workspaceId);
  if (filters.environment) params.set('environment', filters.environment);
  if (filters.criticality) params.set('criticality', filters.criticality);
  if (filters.status) params.set('status', filters.status);
  return apiGet<Page<AdminProjectItem>>(`/api/admin/projects?${params.toString()}`);
}

/** Admin bypass: archives any project regardless of the caller's project
 * role/membership (unlike POST /api/projects/{id}/archive). */
export function archiveProjectAsAdmin(id: string): Promise<Project> {
  return apiPost<Project>(`/api/admin/projects/${id}/archive`);
}

/** A cross-project admin Finding row - a Finding plus its parent project's
 * name, same shape as "My Tasks" (Task 4). */
export interface AdminFindingItem extends Finding {
  project_name: string;
}

export type AdminFindingPreset = 'fixed_this_week';

export interface AdminFindingFilters {
  page?: number;
  pageSize?: number;
  projectId?: string;
  severity?: FindingSeverity;
  status?: FindingStatus;
  assigneeUserId?: string;
  overdue?: boolean;
  fixedSince?: string;
  preset?: AdminFindingPreset;
}

export function listAdminFindings(filters: AdminFindingFilters = {}): Promise<Page<AdminFindingItem>> {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 20));
  if (filters.projectId) params.set('project_id', filters.projectId);
  if (filters.severity) params.set('severity', filters.severity);
  if (filters.status) params.set('status', filters.status);
  if (filters.assigneeUserId) params.set('assignee_user_id', filters.assigneeUserId);
  if (filters.overdue !== undefined) params.set('overdue', String(filters.overdue));
  if (filters.fixedSince) params.set('fixed_since', filters.fixedSince);
  if (filters.preset) params.set('preset', filters.preset);
  return apiGet<Page<AdminFindingItem>>(`/api/admin/findings?${params.toString()}`);
}
