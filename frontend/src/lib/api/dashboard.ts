import { apiGet } from './client';

export interface DashboardCounts {
  documents: number;
  conversations: number;
  messages: number;
  scans: number;
}

export type DashboardActivityType = 'conversation' | 'document' | 'scan';

export interface DashboardActivityItem {
  type: DashboardActivityType;
  id: string;
  title: string;
  detail: string | null;
  created_at: string;
  href: string;
}

export interface DashboardSummaryResponse {
  counts: DashboardCounts;
  recent_activity: DashboardActivityItem[];
}

export function getDashboardSummary(): Promise<DashboardSummaryResponse> {
  return apiGet<DashboardSummaryResponse>('/api/system/dashboard-summary');
}
