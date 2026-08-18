import { authFetch } from '../supabase/authFetch';
import { apiGet, apiPost, ApiError, NetworkUnavailableError } from './client';
import type { Page } from './chatbot';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? '';

export type ReportCategory = 'executive' | 'technical' | 'compliance' | 'incident';
export type ReportFormat = 'markdown' | 'pdf' | 'docx' | 'csv';
export type ReportStatus = 'completed' | 'failed';

export interface ReportTemplate {
  id: string;
  title: string;
  description: string;
  category: ReportCategory;
  sections: string[];
}

export interface ReportRecord {
  id: string;
  title: string;
  category: ReportCategory;
  format: ReportFormat;
  status: ReportStatus;
  sections: string[];
  scope: string;
  content: string;
  error_message: string;
  created_at: string;
  updated_at: string;
}

export interface ReportCreateInput {
  title: string;
  category: ReportCategory;
  format: ReportFormat;
  sections: string[];
  scope?: string;
}

export function listReportTemplates(): Promise<ReportTemplate[]> {
  return apiGet<ReportTemplate[]>('/api/reports/templates');
}

export function listReports(category?: ReportCategory): Promise<Page<ReportRecord>> {
  const params = new URLSearchParams();
  params.set('page', '1');
  params.set('page_size', '100');
  if (category) params.set('category', category);
  return apiGet<Page<ReportRecord>>(`/api/reports?${params.toString()}`);
}

export function createReport(input: ReportCreateInput): Promise<ReportRecord> {
  return apiPost<ReportRecord>('/api/reports', input);
}

export function getReport(id: string): Promise<ReportRecord> {
  return apiGet<ReportRecord>(`/api/reports/${id}`);
}

export async function downloadReportContent(id: string, filenameHint = 'report'): Promise<string> {
  let response: Response;
  try {
    response = await authFetch(`${API_BASE_URL}/api/reports/${id}/download`);
  } catch (cause) {
    if (cause instanceof Error && cause.name === 'UnauthenticatedError') {
      throw cause;
    }
    throw new NetworkUnavailableError(cause);
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = await response.json();
      if (typeof body?.message === 'string') message = body.message;
    } catch {
      // Plain text or empty error body.
    }
    throw new ApiError(response.status, message);
  }
  const blob = await response.blob();
  const contentDisposition = response.headers.get('content-disposition') ?? '';
  const match = /filename="([^"]+)"/.exec(contentDisposition);
  const filename = match?.[1] ?? filenameHint;
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  URL.revokeObjectURL(url);
  return `${filename} (${blob.type || 'application/octet-stream'}, ${blob.size} bytes)`;
}
