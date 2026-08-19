import { apiDelete, apiGet, apiPatch, apiPost } from './client';
import type { Page } from './chatbot';

export type WorkspaceRole = 'owner' | 'admin' | 'member';

export interface Workspace {
  id: string;
  name: string;
  description: string | null;
  created_by_user_id: string;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceMember {
  id: string;
  workspace_id: string;
  user_id: string;
  workspace_role: WorkspaceRole;
  created_at: string;
  updated_at: string;
}

export interface WorkspaceCreateInput {
  name: string;
  description?: string | null;
}

export interface WorkspaceUpdateInput {
  name?: string;
  description?: string | null;
}

export function listWorkspaces(page = 1, pageSize = 20): Promise<Page<Workspace>> {
  return apiGet<Page<Workspace>>(`/api/workspaces?page=${page}&page_size=${pageSize}`);
}

export function getWorkspace(id: string): Promise<Workspace> {
  return apiGet<Workspace>(`/api/workspaces/${id}`);
}

export function createWorkspace(input: WorkspaceCreateInput): Promise<Workspace> {
  return apiPost<Workspace>('/api/workspaces', input);
}

export function updateWorkspace(id: string, input: WorkspaceUpdateInput): Promise<Workspace> {
  return apiPatch<Workspace>(`/api/workspaces/${id}`, input);
}

export function listWorkspaceMembers(workspaceId: string): Promise<{ items: WorkspaceMember[] }> {
  return apiGet<{ items: WorkspaceMember[] }>(`/api/workspaces/${workspaceId}/members`);
}

export function addWorkspaceMember(
  workspaceId: string,
  userId: string,
  workspaceRole: WorkspaceRole,
): Promise<WorkspaceMember> {
  return apiPost<WorkspaceMember>(`/api/workspaces/${workspaceId}/members`, {
    user_id: userId,
    workspace_role: workspaceRole,
  });
}

export function changeWorkspaceMemberRole(
  workspaceId: string,
  userId: string,
  workspaceRole: WorkspaceRole,
): Promise<WorkspaceMember> {
  return apiPatch<WorkspaceMember>(`/api/workspaces/${workspaceId}/members/${userId}`, {
    workspace_role: workspaceRole,
  });
}

export function removeWorkspaceMember(workspaceId: string, userId: string): Promise<void> {
  return apiDelete<void>(`/api/workspaces/${workspaceId}/members/${userId}`);
}
