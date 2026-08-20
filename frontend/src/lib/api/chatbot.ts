import { apiDelete, apiGet, apiPost } from './client';

export interface Conversation {
  id: string;
  title: string;
  actor: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  provider: string | null;
  intent: string | null;
  metadata: Record<string, unknown> | null;
  created_at: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface Citation {
  marker: number;
  document_id: string | null;
  chunk_id: string | null;
  title: string;
  source: string;
  page: number | null;
  heading: string | null;
  chunk_index: number | null;
  score: number;
}

export interface ChatResponse {
  conversation_id: string;
  message_id: string;
  role: string;
  content: string;
  provider: string | null;
  intent: string | null;
  created_at: string;
  request_id: string | null;
  citations: Citation[];
  metadata: Record<string, unknown>;
}

/** Never sends a user id - the backend derives ownership solely from the
 * verified Bearer token (see backend/core/auth.py:get_current_user).
 *
 * `projectId` is optional and only scopes the question to one project (see
 * backend/services/rag/tool_router.py's project-context handlers) - the
 * backend independently re-checks that the caller is actually a member of
 * that project (or a global admin) before answering with any project data,
 * so this is a UX convenience, never a trust boundary by itself. Omit it
 * for a general question unrelated to any specific project. */
export function sendChatMessage(params: {
  message: string;
  conversationId?: string;
  mode: 'fast' | 'deep';
  projectId?: string;
  signal?: AbortSignal;
}): Promise<ChatResponse> {
  return apiPost<ChatResponse>('/api/chatbot/chat', {
    message: params.message,
    conversation_id: params.conversationId ?? null,
    mode: params.mode,
    project_id: params.projectId ?? null,
  }, { signal: params.signal });
}

export function listConversations(page = 1, pageSize = 20): Promise<Page<Conversation>> {
  return apiGet<Page<Conversation>>(`/api/chatbot/conversations?page=${page}&page_size=${pageSize}`);
}

export function createConversation(title: string): Promise<Conversation> {
  return apiPost<Conversation>('/api/chatbot/conversations', { title });
}

export function getConversation(id: string): Promise<Conversation> {
  return apiGet<Conversation>(`/api/chatbot/conversations/${id}`);
}

export function deleteConversation(id: string): Promise<void> {
  return apiDelete(`/api/chatbot/conversations/${id}`);
}

export function listMessages(conversationId: string, page = 1, pageSize = 50): Promise<Page<Message>> {
  return apiGet<Page<Message>>(
    `/api/chatbot/conversations/${conversationId}/messages?page=${page}&page_size=${pageSize}`,
  );
}
