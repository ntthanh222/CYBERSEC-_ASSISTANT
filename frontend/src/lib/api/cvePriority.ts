import { apiGet, apiPost } from './client';

/**
 * Project-scoped CVE risk prioritization (Task 6). Additive on top of the
 * existing, untouched generic CVE Lookup (`./cves.ts`) - this calls a
 * different, project-scoped backend router (`/api/projects/{id}/cve-
 * assessments`), not `/api/cves`.
 */
export type CvePriorityLabel =
  | 'patch_now'
  | 'high'
  | 'medium'
  | 'low'
  | 'not_affected'
  | 'needs_review';

export interface CveAssessment {
  id: string;
  project_id: string;
  cve_id: string;
  cvss_score: number | null;
  epss_score: number | null;
  is_kev: boolean;
  affected_version: string | null;
  fixed_version: string | null;
  technology: string | null;
  priority: CvePriorityLabel;
  score: number;
  rationale: Record<string, unknown>;
  finding_id: string | null;
  created_at: string;
  updated_at: string;
}

/** owner/security only: run (or re-run) a project-aware CVE risk assessment. */
export function assessCve(
  projectId: string,
  cveId: string,
  affectedVersion?: string | null,
): Promise<CveAssessment> {
  return apiPost<CveAssessment>(`/api/projects/${projectId}/cve-assessments`, {
    cve_id: cveId,
    affected_version: affectedVersion ?? null,
  });
}

/** Any project member: list every assessment recorded for this project. */
export function listCveAssessments(projectId: string): Promise<CveAssessment[]> {
  return apiGet<CveAssessment[]>(`/api/projects/${projectId}/cve-assessments`);
}

/** Any project member: fetch one project's assessment detail for a CVE. */
export function getCveAssessment(projectId: string, cveId: string): Promise<CveAssessment> {
  return apiGet<CveAssessment>(
    `/api/projects/${projectId}/cve-assessments/${encodeURIComponent(cveId)}`,
  );
}
