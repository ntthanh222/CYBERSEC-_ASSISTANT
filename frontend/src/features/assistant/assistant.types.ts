import type { AIMessage } from '../../types/data-provider.types';

export interface ChatSession {
  id: string;
  title: string;
  updated_at: string;
  messages: AIMessage[];
  is_pinned?: boolean;
}
