import { apiDelete, apiGet, apiPost, apiPostForm } from './client';
import type { Page } from './chatbot';

export type ProcessingStatus = 'pending' | 'processing' | 'ready' | 'failed';

export interface KnowledgeDocument {
  id: string;
  owner_user_id: string | null;
  title: string;
  source_type: 'upload' | 'system';
  source_name: string;
  mime_type: string;
  processing_status: ProcessingStatus;
  error_message: string | null;
  page_count: number | null;
  chunk_count: number;
  created_at: string;
  updated_at: string;
}

export interface DocumentUploadResponse {
  document: KnowledgeDocument;
  reused_existing: boolean;
}

export interface RetrievedChunk {
  document_id: string;
  document_title: string;
  chunk_id: string;
  chunk_index: number | null;
  page: number | null;
  heading: string | null;
  content: string;
  score: number;
}

export interface RetrievalPreviewResponse {
  query: string;
  results: RetrievedChunk[];
  retrieval_metadata: Record<string, unknown>;
}

/** Never sends an owner id - the backend derives ownership solely from the
 * verified Bearer token. */
export function uploadDocument(file: File, title?: string): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append('file', file);
  if (title) {
    form.append('title', title);
  }
  return apiPostForm<DocumentUploadResponse>('/api/knowledge/documents', form);
}

export function listDocuments(page = 1, pageSize = 20): Promise<Page<KnowledgeDocument>> {
  return apiGet<Page<KnowledgeDocument>>(
    `/api/knowledge/documents?page=${page}&page_size=${pageSize}`,
  );
}

export function getDocument(id: string): Promise<KnowledgeDocument> {
  return apiGet<KnowledgeDocument>(`/api/knowledge/documents/${id}`);
}

export function deleteDocument(id: string): Promise<void> {
  return apiDelete(`/api/knowledge/documents/${id}`);
}

export function reprocessDocument(id: string): Promise<KnowledgeDocument> {
  return apiPost<KnowledgeDocument>(`/api/knowledge/documents/${id}/reprocess`);
}

export function previewRetrieval(query: string, limit = 5): Promise<RetrievalPreviewResponse> {
  return apiPost<RetrievalPreviewResponse>('/api/knowledge/retrieval/preview', { query, limit });
}
