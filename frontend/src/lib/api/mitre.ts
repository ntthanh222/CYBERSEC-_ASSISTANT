import { apiGet, apiPatch, apiPost } from './client';
import type { Page } from './chatbot';

export type CoverageStatus = 'planned' | 'partial' | 'covered' | 'gap';

export interface MitreTechnique {
  id: string;
  incident_id: string | null;
  technique_id: string;
  tactic: string;
  name: string;
  description: string;
  detection: string;
  mitigation: string;
  coverage_status: CoverageStatus;
  data_sources: string[];
  created_at: string;
  updated_at: string;
}

export interface MitreMatrix {
  summary: {
    total: number;
    covered: number;
    partial: number;
    planned: number;
    gaps: number;
  };
  tactics: Record<string, MitreTechnique[]>;
}

export interface MitreTechniqueInput {
  incident_id?: string | null;
  technique_id: string;
  tactic: string;
  name: string;
  description?: string;
  detection?: string;
  mitigation?: string;
  coverage_status?: CoverageStatus;
  data_sources?: string[];
}

export function getMitreMatrix(): Promise<MitreMatrix> {
  return apiGet<MitreMatrix>('/api/mitre/matrix');
}

export function listMitreTechniques(filters: {
  search?: string;
  tactic?: string;
  coverage_status?: CoverageStatus;
  incident_id?: string;
} = {}): Promise<Page<MitreTechnique>> {
  const params = new URLSearchParams();
  params.set('page', '1');
  params.set('page_size', '100');
  if (filters.search) params.set('search', filters.search);
  if (filters.tactic) params.set('tactic', filters.tactic);
  if (filters.coverage_status) params.set('coverage_status', filters.coverage_status);
  if (filters.incident_id) params.set('incident_id', filters.incident_id);
  return apiGet<Page<MitreTechnique>>(`/api/mitre/techniques?${params.toString()}`);
}

export function createMitreTechnique(input: MitreTechniqueInput): Promise<MitreTechnique> {
  return apiPost<MitreTechnique>('/api/mitre/techniques', input);
}

export function getMitreTechnique(id: string): Promise<MitreTechnique> {
  return apiGet<MitreTechnique>(`/api/mitre/techniques/${id}`);
}

export function updateMitreTechnique(
  id: string,
  input: Pick<MitreTechnique, 'detection' | 'mitigation' | 'coverage_status' | 'data_sources'> &
    Partial<Pick<MitreTechnique, 'incident_id'>>,
): Promise<MitreTechnique> {
  return apiPatch<MitreTechnique>(`/api/mitre/techniques/${id}`, input);
}

export function linkMitreTechniqueToIncident(technique: MitreTechnique, incidentId: string): Promise<MitreTechnique> {
  return updateMitreTechnique(technique.id, {
    incident_id: incidentId,
    detection: technique.detection,
    mitigation: technique.mitigation,
    coverage_status: technique.coverage_status,
    data_sources: technique.data_sources,
  });
}
