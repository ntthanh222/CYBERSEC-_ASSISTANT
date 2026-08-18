import { apiGet, apiPatch, apiPost } from './client';
import type { Page } from './chatbot';

export type Severity = 'low' | 'medium' | 'high' | 'critical';
export type PatchStatus = 'not_started' | 'in_progress' | 'patched' | 'accepted_risk';

export interface VulnerabilityRecord {
  id: string;
  asset_id: string | null;
  cve_id: string;
  title: string;
  description: string;
  cvss: number;
  severity: Severity;
  published_date: string;
  updated_date: string;
  references: string[];
  affected_products: string[];
  remediation: string;
  watchlist: boolean;
  created_at: string;
  updated_at: string;
}

export interface VulnerabilityCreateInput {
  asset_id?: string | null;
  cve_id: string;
  title: string;
  description: string;
  cvss: number;
  severity: Severity;
  published_date: string;
  updated_date: string;
  references?: string[];
  affected_products?: string[];
  remediation?: string;
  watchlist?: boolean;
}

export interface PatchTask {
  id: string;
  vulnerability_id: string;
  cve_id: string;
  title: string;
  cvss: number;
  asset_id: string | null;
  asset_name: string;
  status: PatchStatus;
  notes: string;
  created_at: string;
  updated_at: string;
}

export function listVulnerabilities(filters: {
  search?: string;
  severity?: Severity;
  watchlist?: boolean;
  pageSize?: number;
} = {}): Promise<Page<VulnerabilityRecord>> {
  const params = new URLSearchParams();
  params.set('page', '1');
  params.set('page_size', String(filters.pageSize ?? 50));
  if (filters.search) params.set('search', filters.search);
  if (filters.severity) params.set('severity', filters.severity);
  if (typeof filters.watchlist === 'boolean') params.set('watchlist', String(filters.watchlist));
  return apiGet<Page<VulnerabilityRecord>>(`/api/vulnerabilities?${params.toString()}`);
}

export function getVulnerability(id: string): Promise<VulnerabilityRecord> {
  return apiGet<VulnerabilityRecord>(`/api/vulnerabilities/items/${id}`);
}

export function createVulnerability(input: VulnerabilityCreateInput): Promise<VulnerabilityRecord> {
  return apiPost<VulnerabilityRecord>('/api/vulnerabilities', input);
}

export function setVulnerabilityWatchlist(id: string, watchlist: boolean): Promise<VulnerabilityRecord> {
  return apiPatch<VulnerabilityRecord>(`/api/vulnerabilities/items/${id}/watchlist`, { watchlist });
}

export function listPatchTasks(): Promise<Page<PatchTask>> {
  return apiGet<Page<PatchTask>>('/api/vulnerabilities/patch-tasks/list?page=1&page_size=100');
}

export function createPatchTask(input: {
  vulnerability_id: string;
  asset_name?: string;
  status?: PatchStatus;
  notes?: string;
}): Promise<PatchTask> {
  return apiPost<PatchTask>('/api/vulnerabilities/patch-tasks', input);
}

export function setPatchTaskStatus(id: string, status: PatchStatus): Promise<{ status: string }> {
  return apiPatch<{ status: string }>(`/api/vulnerabilities/patch-tasks/${id}`, { status });
}
