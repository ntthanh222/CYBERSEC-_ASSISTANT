import { apiGet, apiPost } from './client';
import type { Page } from './chatbot';

export type ScanRunStatus = 'queued' | 'running' | 'completed' | 'failed';
export type ScanType = 'url_scan';

/** Rescan diff classification labels (Task 3) - each maps to a list of
 * Finding IDs. Always present as keys on a completed scan's `diff`, even
 * when empty (a scan with no previous_scan_run_id still has the shape,
 * just with `new_regression`/`reopened_regression`/etc all empty and
 * `new` holding everything). */
export interface ScanDiffSummary {
  still_open: string[];
  new: string[];
  new_regression: string[];
  reopened_regression: string[];
  fixed_pending_verify: string[];
  absent_unconfirmed: string[];
  regressed_but_dismissed: string[];
  regressed_after_close: string[];
}

export interface ScanRunSummary {
  // Severity counts (low/medium/high/critical) from Task 2, plus the
  // Task 3 diff - both live in the same object server-side.
  low?: number;
  medium?: number;
  high?: number;
  critical?: number;
  diff?: ScanDiffSummary;
  diff_counts?: Record<string, number>;
  error?: string;
}

export interface ScanRun {
  id: string;
  project_id: string;
  triggered_by_user_id: string;
  scan_type: ScanType;
  target: string;
  status: ScanRunStatus;
  started_at: string | null;
  completed_at: string | null;
  summary: ScanRunSummary;
  previous_scan_run_id: string | null;
  created_at: string;
  updated_at: string;
}

export function triggerScan(
  projectId: string,
  target: string,
  previousScanRunId?: string,
): Promise<ScanRun> {
  return apiPost<ScanRun>(`/api/projects/${projectId}/scans`, {
    target,
    previous_scan_run_id: previousScanRunId ?? null,
  });
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
