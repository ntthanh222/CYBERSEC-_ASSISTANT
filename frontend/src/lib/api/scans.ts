import { apiGet, apiPost } from './client';
import type { Page } from './chatbot';

export type ScanRunStatus = 'queued' | 'running' | 'completed' | 'failed';
export type ScanType = 'url_scan';

export interface ScanRun {
  id: string;
  project_id: string;
  triggered_by_user_id: string;
  scan_type: ScanType;
  target: string;
  status: ScanRunStatus;
  started_at: string | null;
  completed_at: string | null;
  summary: Record<string, number | string>;
  previous_scan_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export function triggerScan(projectId: string, target: string): Promise<ScanRun> {
  return apiPost<ScanRun>(`/api/projects/${projectId}/scans`, { target });
}

export function listScans(
  projectId: string,
  params: { page?: number; pageSize?: number } = {},
): Promise<Page<ScanRun>> {
  const query = new URLSearchParams();
  query.set('page', String(params.page ?? 1));
  query.set('page_size', String(params.pageSize ?? 20));
  return apiGet<Page<ScanRun>>(`/api/projects/${projectId}/scans?${query.toString()}`);
}

export function getScan(projectId: string, scanId: string): Promise<ScanRun> {
  return apiGet<ScanRun>(`/api/projects/${projectId}/scans/${scanId}`);
}
