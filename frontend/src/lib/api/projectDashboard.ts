import { apiGet } from './client';
import type { Finding } from './findings';

/** Matches backend.schemas.project_dashboard.SeverityBreakdown exactly. */
export interface SeverityBreakdown {
  critical: number;
  high: number;
  medium: number;
  low: number;
}

/** Matches backend.schemas.project_dashboard.LatestScanSummary exactly. */
export interface LatestScanSummary {
  id: string;
  status: string;
  target: string;
  completed_at: string | null;
  summary: Record<string, unknown>;
}

/** Matches backend.schemas.project_dashboard.SecurityTrendPoint exactly. */
export interface SecurityTrendPoint {
  scan_run_id: string;
  completed_at: string | null;
  open_count: number;
  score: number;
}

/** Matches backend.schemas.project_dashboard.AssigneeWorkload exactly. */
export interface AssigneeWorkload {
  assignee_user_id: string;
  open_count: number;
}

/** Matches backend.schemas.project_dashboard.ProjectSecurityDashboard exactly -
 * every field here is a real aggregation query result, never a placeholder. */
export interface ProjectSecurityDashboard {
  project_id: string;
  security_score: number;
  open_findings: number;
  open_by_severity: SeverityBreakdown;
  waiting_verify: number;
  overdue: number;
  fixed_this_week: number;
  latest_scan: LatestScanSummary | null;
  security_trend: SecurityTrendPoint[];
  top_risks: Finding[];
  latest_findings: Finding[];
  assigned_open: number;
  assigned_open_by_assignee: AssigneeWorkload[];
}

export function getProjectDashboard(projectId: string): Promise<ProjectSecurityDashboard> {
  return apiGet<ProjectSecurityDashboard>(`/api/projects/${projectId}/dashboard`);
}
