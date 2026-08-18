import { apiDelete, apiGet } from './client';
import type { Page } from './chatbot';

export interface ScanHistoryRecord {
  id: string;
  scan_type: 'url_scan' | 'cve_lookup';
  target: string;
  status: 'completed' | 'failed';
  risk_score: number | null;
  severity: 'low' | 'medium' | 'high' | 'critical' | null;
  summary: string;
  details: Record<string, unknown> | null;
  actor: string | null;
  created_at: string;
}

export interface ScanHistoryFilters {
  page?: number;
  pageSize?: number;
  scanType?: 'url_scan' | 'cve_lookup';
  status?: 'completed' | 'failed';
  severity?: 'low' | 'medium' | 'high' | 'critical';
  sort?: 'asc' | 'desc';
}

export function listScanHistory(filters: ScanHistoryFilters = {}): Promise<Page<ScanHistoryRecord>> {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 20));
  if (filters.scanType) params.set('scan_type', filters.scanType);
  if (filters.status) params.set('status', filters.status);
  if (filters.severity) params.set('severity', filters.severity);
  if (filters.sort) params.set('sort', filters.sort);
  return apiGet<Page<ScanHistoryRecord>>(`/api/tools/scan-history?${params.toString()}`);
}

export function getScanHistoryRecord(id: string): Promise<ScanHistoryRecord> {
  return apiGet<ScanHistoryRecord>(`/api/tools/scan-history/${id}`);
}

export function deleteScanHistoryRecord(id: string): Promise<void> {
  return apiDelete(`/api/tools/scan-history/${id}`);
}
