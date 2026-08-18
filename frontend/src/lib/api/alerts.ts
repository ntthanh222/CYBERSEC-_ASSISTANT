import { apiGet, apiPatch, apiPost } from './client';
import type { Page } from './chatbot';

export type AlertSeverity = 'low' | 'medium' | 'high' | 'critical';
export type AlertStatus = 'new' | 'acknowledged' | 'investigating' | 'resolved' | 'false_positive';

export interface AlertRecord {
  id: string;
  title: string;
  description: string;
  severity: AlertSeverity;
  source: string;
  status: AlertStatus;
  asset_id: string | null;
  vulnerability_id: string | null;
  asset_name: string;
  ioc_value: string;
  evidence: string;
  created_at: string;
  updated_at: string;
}

export interface AlertCreateInput {
  title: string;
  description: string;
  severity: AlertSeverity;
  source: string;
  status?: AlertStatus;
  asset_id?: string | null;
  vulnerability_id?: string | null;
  asset_name?: string;
  ioc_value?: string;
  evidence?: string;
}

export function listAlerts(filters: {
  search?: string;
  severity?: AlertSeverity;
  status?: AlertStatus;
} = {}): Promise<Page<AlertRecord>> {
  const params = new URLSearchParams();
  params.set('page', '1');
  params.set('page_size', '100');
  if (filters.search) params.set('search', filters.search);
  if (filters.severity) params.set('severity', filters.severity);
  if (filters.status) params.set('status', filters.status);
  return apiGet<Page<AlertRecord>>(`/api/alerts?${params.toString()}`);
}

export function createAlert(input: AlertCreateInput): Promise<AlertRecord> {
  return apiPost<AlertRecord>('/api/alerts', input);
}

export function getAlert(id: string): Promise<AlertRecord> {
  return apiGet<AlertRecord>(`/api/alerts/${id}`);
}

export function setAlertStatus(id: string, status: AlertStatus): Promise<AlertRecord> {
  return apiPatch<AlertRecord>(`/api/alerts/${id}/status`, { status });
}
