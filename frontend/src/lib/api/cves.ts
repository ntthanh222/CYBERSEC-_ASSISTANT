import { apiGet } from './client';

export interface CveResult {
  cve_id: string;
  description: string;
  published_at: string | null;
  modified_at: string | null;
  cvss_score: number | null;
  severity: 'low' | 'medium' | 'high' | 'critical' | null;
  vector: string | null;
  affected_products: string[];
  references: string[];
  source: string;
  cached: boolean;
  fetched_at: string;
}

export interface CveSearchResponse {
  query: string;
  results: CveResult[];
  count: number;
}

export function searchCves(query: string, limit = 10): Promise<CveSearchResponse> {
  return apiGet<CveSearchResponse>(
    `/api/cves/search?q=${encodeURIComponent(query)}&limit=${limit}`,
  );
}

export function getCve(cveId: string): Promise<CveResult> {
  return apiGet<CveResult>(`/api/cves/${encodeURIComponent(cveId)}`);
}
