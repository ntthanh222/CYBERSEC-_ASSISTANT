import { apiGet, apiPost } from './client';
import type { Page } from './chatbot';

export type AssetType = 'server' | 'workstation' | 'cloud_resource' | 'database' | 'network_device';
export type BusinessCriticality = 'low' | 'medium' | 'high' | 'critical';
export type PatchStatus =
  | 'unknown'
  | 'not_started'
  | 'in_progress'
  | 'patched'
  | 'accepted_risk'
  | 'not_applicable';
export type ExploitEvidence =
  | 'none'
  | 'unconfirmed'
  | 'public_poc'
  | 'active_exploitation'
  | 'internal_confirmation';

export interface AssetRecord {
  id: string;
  name: string;
  type: AssetType;
  hostname: string;
  ip_address: string;
  operating_system: string;
  owner: string;
  department: string;
  business_criticality: BusinessCriticality;
  internet_exposed: boolean;
  description: string;
  linked_cves: string[];
  patch_status: PatchStatus | null;
  exploit_evidence: ExploitEvidence | null;
  created_at: string;
  updated_at: string;
}

export interface AssetCreateInput {
  name: string;
  type: AssetType;
  hostname: string;
  ip_address: string;
  operating_system: string;
  owner: string;
  department: string;
  business_criticality: BusinessCriticality;
  internet_exposed?: boolean;
  description?: string;
  linked_cves?: string[];
  patch_status?: PatchStatus | null;
  exploit_evidence?: ExploitEvidence | null;
}

export interface AssetFilters {
  page?: number;
  pageSize?: number;
  type?: AssetType;
  businessCriticality?: BusinessCriticality;
  sort?: 'asc' | 'desc';
}

export function listAssets(filters: AssetFilters = {}): Promise<Page<AssetRecord>> {
  const params = new URLSearchParams();
  params.set('page', String(filters.page ?? 1));
  params.set('page_size', String(filters.pageSize ?? 20));
  if (filters.type) params.set('type', filters.type);
  if (filters.businessCriticality) params.set('business_criticality', filters.businessCriticality);
  if (filters.sort) params.set('sort', filters.sort);
  return apiGet<Page<AssetRecord>>(`/api/assets?${params.toString()}`);
}

export function getAsset(id: string): Promise<AssetRecord> {
  return apiGet<AssetRecord>(`/api/assets/${id}`);
}

export function createAsset(input: AssetCreateInput): Promise<AssetRecord> {
  return apiPost<AssetRecord>('/api/assets', input);
}
