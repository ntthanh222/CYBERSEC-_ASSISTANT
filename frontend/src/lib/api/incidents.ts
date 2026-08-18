import { apiGet, apiPatch, apiPost } from './client';
import type { Page } from './chatbot';

export type IncidentSeverity = 'low' | 'medium' | 'high' | 'critical';
export type IncidentStatus = 'open' | 'triaged' | 'in_progress' | 'contained' | 'eradicated' | 'recovered' | 'closed';
export type IncidentTaskStatus = 'pending' | 'in_progress' | 'completed' | 'blocked';

export interface IncidentRecord {
  id: string;
  title: string;
  description: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  assignee: string;
  source_alert_id: string | null;
  asset_name: string;
  cve_id: string;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
}

export interface IncidentTask {
  id: string;
  incident_id: string;
  title: string;
  description: string;
  status: IncidentTaskStatus;
  owner: string;
  created_at: string;
  updated_at: string;
}

export interface IncidentTimelineEvent {
  id: string;
  incident_id: string;
  event_type: string;
  message: string;
  actor: string;
  created_at: string;
}

export interface IncidentDetail extends IncidentRecord {
  tasks: IncidentTask[];
  timeline: IncidentTimelineEvent[];
}

export interface IncidentCreateInput {
  title: string;
  description: string;
  severity: IncidentSeverity;
  status?: IncidentStatus;
  assignee?: string;
  source_alert_id?: string | null;
  asset_name?: string;
  cve_id?: string;
}

export interface IncidentTaskInput {
  title: string;
  description?: string;
  status?: IncidentTaskStatus;
  owner?: string;
}

export function listIncidents(filters: {
  search?: string;
  severity?: IncidentSeverity;
  status?: IncidentStatus;
} = {}): Promise<Page<IncidentRecord>> {
  const params = new URLSearchParams();
  params.set('page', '1');
  params.set('page_size', '100');
  if (filters.search) params.set('search', filters.search);
  if (filters.severity) params.set('severity', filters.severity);
  if (filters.status) params.set('status', filters.status);
  return apiGet<Page<IncidentRecord>>(`/api/incidents?${params.toString()}`);
}

export function createIncident(input: IncidentCreateInput): Promise<IncidentRecord> {
  return apiPost<IncidentRecord>('/api/incidents', input);
}

export function getIncident(id: string): Promise<IncidentDetail> {
  return apiGet<IncidentDetail>(`/api/incidents/${id}`);
}

export function setIncidentStatus(id: string, status: IncidentStatus): Promise<IncidentRecord> {
  return apiPatch<IncidentRecord>(`/api/incidents/${id}/status`, { status });
}

export function createIncidentTask(incidentId: string, input: IncidentTaskInput): Promise<IncidentTask> {
  return apiPost<IncidentTask>(`/api/incidents/${incidentId}/tasks`, input);
}

export function setIncidentTaskStatus(id: string, status: IncidentTaskStatus): Promise<IncidentTask> {
  return apiPatch<IncidentTask>(`/api/incidents/tasks/${id}`, { status });
}

export function addIncidentNote(incidentId: string, message: string): Promise<IncidentTimelineEvent> {
  return apiPost<IncidentTimelineEvent>(`/api/incidents/${incidentId}/notes`, { message });
}
