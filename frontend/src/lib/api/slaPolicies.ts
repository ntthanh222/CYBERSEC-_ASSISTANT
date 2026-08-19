import { apiGet, apiPatch, apiPut } from './client';
import type { FindingSeverity } from './findings';

export interface SlaPolicy {
  id: string;
  project_id: string | null;
  severity: FindingSeverity;
  hours_to_deadline: number;
  created_at: string;
  updated_at: string;
}

export type EffectiveSlaPolicySource = 'project_override' | 'global_default' | 'none';

export interface EffectiveSlaPolicy {
  severity: FindingSeverity;
  hours_to_deadline: number | null;
  source: EffectiveSlaPolicySource;
}

/** Admin-only: list the global default policies. */
export function listGlobalSlaPolicies(): Promise<SlaPolicy[]> {
  return apiGet<SlaPolicy[]>('/api/admin/sla-policies');
}

/** Admin-only: set a global default's hours_to_deadline (creates the row if missing). */
export function updateGlobalSlaPolicy(
  severity: FindingSeverity,
  hoursToDeadline: number,
): Promise<SlaPolicy> {
  return apiPatch<SlaPolicy>(`/api/admin/sla-policies/${severity}`, {
    hours_to_deadline: hoursToDeadline,
  });
}

/** Any project member: the effective (override-merged-with-default) policy per severity. */
export function getEffectiveSlaPolicies(projectId: string): Promise<EffectiveSlaPolicy[]> {
  return apiGet<EffectiveSlaPolicy[]>(`/api/projects/${projectId}/sla-policies`);
}

/** owner/security only: set (or, with `hoursToDeadline: null`, clear) a project override. */
export function setProjectSlaOverride(
  projectId: string,
  severity: FindingSeverity,
  hoursToDeadline: number | null,
): Promise<EffectiveSlaPolicy> {
  return apiPut<EffectiveSlaPolicy>(`/api/projects/${projectId}/sla-policies/${severity}`, {
    hours_to_deadline: hoursToDeadline,
  });
}
