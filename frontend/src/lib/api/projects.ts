import { apiDelete, apiGet, apiPatch, apiPost } from './client';
import type { Page } from './chatbot';

export type ProjectEnvironment = 'development' | 'staging' | 'production';
export type ProjectCriticality = 'low' | 'medium' | 'high' | 'critical';
export type ProjectStatus = 'active' | 'archived';
export type ProjectRole = 'owner' | 'security' | 'developer' | 'viewer';

export interface Technology {
  name: string;
  version: string;
}

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  domain: string | null;
  environment: ProjectEnvironment;
  criticality: ProjectCriticality;
  internet_facing: boolean;
  technologies: Technology[];
  status: ProjectStatus;
  archived_at: string | null;
  owner_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface ProjectMember {
  id: string;
  project_id: string;
  user_id: string;
  project_role: ProjectRole;
  created_at: string;
  updated_at: string;
}

export interface ProjectCreateInput {
  workspace_id: string;
  name: string;
  domain?: string | null;
  environment: ProjectEnvironment;
  criticality: ProjectCriticality;
  internet_facing?: boolean;
  technologies?: Technology[];
}

export interface ProjectUpdateInput {
  name?: string;
  domain?: string | null;
  environment?: ProjectEnvironment;
  criticality?: ProjectCriticality;
  internet_facing?: boolean;
  technologies?: Technology[];
}

export interface ProjectFilters {
  page?: number;
  pageSize?: number;
  workspaceId?: string;
  includeArchived?: boolean;
}

export function listProjects(filters: ProjectFilters = {}): Promise<Page<Project>> {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 20));
  if (filters.workspaceId) params.set('workspace_id', filters.workspaceId);
  if (filters.includeArchived) params.set('include_archived', 'true');
  return apiGet<Page<Project>>(`/api/projects?${params.toString()}`);
}

export function getProject(id: string): Promise<Project> {
  return apiGet<Project>(`/api/projects/${id}`);
}

export function createProject(input: ProjectCreateInput): Promise<Project> {
  return apiPost<Project>('/api/projects', input);
}

export function updateProject(id: string, input: ProjectUpdateInput): Promise<Project> {
  return apiPatch<Project>(`/api/projects/${id}`, input);
}

export function archiveProject(id: string): Promise<Project> {
  return apiPost<Project>(`/api/projects/${id}/archive`);
}

export function listProjectMembers(projectId: string): Promise<{ items: ProjectMember[] }> {
  return apiGet<{ items: ProjectMember[] }>(`/api/projects/${projectId}/members`);
}

export function addProjectMember(
  projectId: string,
  userId: string,
  projectRole: ProjectRole,
): Promise<ProjectMember> {
  return apiPost<ProjectMember>(`/api/projects/${projectId}/members`, {
    user_id: userId,
    project_role: projectRole,
  });
}

export function changeProjectMemberRole(
  projectId: string,
  userId: string,
  projectRole: ProjectRole,
): Promise<ProjectMember> {
  return apiPatch<ProjectMember>(`/api/projects/${projectId}/members/${userId}`, {
    project_role: projectRole,
  });
}

export function removeProjectMember(projectId: string, userId: string): Promise<void> {
  return apiDelete<void>(`/api/projects/${projectId}/members/${userId}`);
}
