import { apiGet, apiPatch, apiPost } from './client';
import type { Page } from './chatbot';

export interface SecurityNewsArticle {
  id: string;
  title: string;
  summary: string;
  ai_summary: string;
  url: string;
  source: string;
  published_at: string;
  category: string;
  related_cves: string[];
  bookmarked: boolean;
  read: boolean;
  created_at: string;
  updated_at: string;
}

export interface SecurityNewsInput {
  title: string;
  summary: string;
  ai_summary?: string;
  url: string;
  source: string;
  published_at: string;
  category?: string;
  related_cves?: string[];
  bookmarked?: boolean;
  read?: boolean;
}

export function listSecurityNews(filters: {
  search?: string;
  bookmarked?: boolean;
  unread?: boolean;
} = {}): Promise<Page<SecurityNewsArticle>> {
  const params = new URLSearchParams();
  params.set('page', '1');
  params.set('page_size', '100');
  if (filters.search) params.set('search', filters.search);
  if (filters.bookmarked !== undefined) params.set('bookmarked', String(filters.bookmarked));
  if (filters.unread !== undefined) params.set('unread', String(filters.unread));
  return apiGet<Page<SecurityNewsArticle>>(`/api/news?${params.toString()}`);
}

export function createSecurityNews(input: SecurityNewsInput): Promise<SecurityNewsArticle> {
  return apiPost<SecurityNewsArticle>('/api/news', input);
}

export function getSecurityNews(id: string): Promise<SecurityNewsArticle> {
  return apiGet<SecurityNewsArticle>(`/api/news/${id}`);
}

export function setSecurityNewsBookmark(id: string, bookmarked: boolean): Promise<SecurityNewsArticle> {
  return apiPatch<SecurityNewsArticle>(`/api/news/${id}/bookmark`, { bookmarked });
}

export function setSecurityNewsRead(id: string, read: boolean): Promise<SecurityNewsArticle> {
  return apiPatch<SecurityNewsArticle>(`/api/news/${id}/read`, { read });
}
