import { apiGet, apiPatch, apiPost } from './client';
import type { Page } from './chatbot';

export type IOCType = 'ip' | 'domain' | 'url' | 'sha256';
export type IOCSeverity = 'low' | 'medium' | 'high' | 'critical';
export type IOCConfidence = 'low' | 'medium' | 'high';

export interface RiskPoint {
  time: string;
  score: number;
}

export interface ThreatIOC {
  id: string;
  type: IOCType;
  value: string;
  severity: IOCSeverity;
  confidence: IOCConfidence;
  description: string;
  source: string;
  first_seen: string;
  last_seen: string;
  watchlist: boolean;
  tags: string[];
  mitre_techniques: string[];
  risk_timeline: RiskPoint[];
  created_at: string;
  updated_at: string;
}

export interface ThreatIOCCreateInput {
  type: IOCType;
  value: string;
  severity: IOCSeverity;
  confidence: IOCConfidence;
  description?: string;
  source: string;
  first_seen: string;
  last_seen: string;
  watchlist?: boolean;
  tags?: string[];
  mitre_techniques?: string[];
  risk_timeline?: RiskPoint[];
}

export interface ThreatIOCFilters {
  page?: number;
  pageSize?: number;
  search?: string;
  type?: IOCType;
  severity?: IOCSeverity;
  watchlist?: boolean;
}

export interface ThreatIntelSummary {
  total: number;
  critical: number;
  watchlist: number;
  recent_48h: number;
  items: ThreatIOC[];
}

export function listThreatIOCs(filters: ThreatIOCFilters = {}): Promise<Page<ThreatIOC>> {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 20));
  if (filters.search) params.set('search', filters.search);
  if (filters.type) params.set('type', filters.type);
  if (filters.severity) params.set('severity', filters.severity);
  if (typeof filters.watchlist === 'boolean') params.set('watchlist', String(filters.watchlist));
  return apiGet<Page<ThreatIOC>>(`/api/threat-intel/iocs?${params.toString()}`);
}

export function getThreatIOC(id: string): Promise<ThreatIOC> {
  return apiGet<ThreatIOC>(`/api/threat-intel/iocs/${id}`);
}

export function createThreatIOC(input: ThreatIOCCreateInput): Promise<ThreatIOC> {
  return apiPost<ThreatIOC>('/api/threat-intel/iocs', input);
}

export function setThreatIOCWatchlist(id: string, watchlist: boolean): Promise<ThreatIOC> {
  return apiPatch<ThreatIOC>(`/api/threat-intel/iocs/${id}/watchlist`, { watchlist });
}

export function getThreatIntelSummary(): Promise<ThreatIntelSummary> {
  return apiGet<ThreatIntelSummary>('/api/threat-intel/summary');
}
