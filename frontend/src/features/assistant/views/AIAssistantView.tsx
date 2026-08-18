import React, { useState, useEffect, useCallback, useRef } from 'react';
import { Link, useLocation } from 'react-router-dom';
import type { ChatSession } from '../assistant.types';
import type { AIMessage } from '../../../types/data-provider.types';
import {
  listConversations,
  createConversation,
  deleteConversation,
  listMessages,
  sendChatMessage,
} from '../../../lib/api/chatbot';
import type { Conversation, Message } from '../../../lib/api/chatbot';
import { ApiError } from '../../../lib/api/client';
import { ConversationSidebar } from '../components/ConversationSidebar';
import { ConversationArea } from '../components/ConversationArea';
import { Composer } from '../components/Composer';
import { KnowledgeBaseView } from '../../knowledge-base/views/KnowledgeBaseView';
import { Sparkles, AlertTriangle, PanelLeft, BookOpen, MessageSquare } from 'lucide-react';

const SIDEBAR_OPEN_STORAGE_KEY = 'cybersec_ai_sidebar_open';

//: Below this width the conversation-history sidebar is a fixed 256px panel
// that has no room to coexist with the composer - matches the `md` Tailwind
// breakpoint the app's main navigation sidebar already collapses at.
const MOBILE_SIDEBAR_BREAKPOINT_PX = 768;

function readStoredSidebarOpen(): boolean {
  try {
    const stored = localStorage.getItem(SIDEBAR_OPEN_STORAGE_KEY);
    if (stored !== null) {
      return stored === 'true';
    }
  } catch {
    // localStorage unavailable - fall through to the viewport-based default.
  }
  // No saved preference yet: default open on desktop, closed on mobile so a
  // first-time mobile visit doesn't push the composer off-screen.
  return typeof window === 'undefined' || window.innerWidth >= MOBILE_SIDEBAR_BREAKPOINT_PX;
}

const suggestedPrompts = [
  'Làm thế nào để giảm thiểu rủi ro JNDI của Apache Log4j CVE-2021-44228?',
  'Tôi nên kiểm tra gì đầu tiên khi có báo cáo về một liên kết lừa đảo?',
  'Giải thích cách thức hoạt động của tấn công SSRF và cách phát hiện chúng.',
];

function toAIMessage(message: Message): AIMessage {
  return {
    id: message.id,
    sender: message.role === 'user' ? 'user' : 'assistant',
    content: message.content,
    timestamp: message.created_at,
    provider: message.provider ?? undefined,
  };
}

function toChatSession(conversation: Conversation, messages: AIMessage[] = []): ChatSession {
  return {
    id: conversation.id,
    title: conversation.title,
    updated_at: conversation.updated_at,
    messages,
  };
}

export const AIAssistantView: React.FC = () => {
  const location = useLocation();
  const knowledgeTab = location.pathname.startsWith('/ai/knowledge');
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string>('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [isLoadingSessions, setIsLoadingSessions] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [isSidebarOpen, setIsSidebarOpen] = useState(readStoredSidebarOpen);
  const abortControllerRef = useRef<AbortController | null>(null);

  useEffect(() => {
    try {
      localStorage.setItem(SIDEBAR_OPEN_STORAGE_KEY, String(isSidebarOpen));
    } catch {
      // localStorage unavailable (private browsing, quota) - collapse state
      // just won't persist across refresh, which is a graceful degradation.
    }
  }, [isSidebarOpen]);

  useEffect(() => {
    listConversations()
      .then((page) => {
        const conversations = page.items.map((conversation) => toChatSession(conversation));
        setSessions(conversations);
        if (conversations.length > 0) {
          setActiveSessionId(conversations[0].id);
        }
      })
      .catch((err) => {
        setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải danh sách cuộc trò chuyện.');
      })
      .finally(() => setIsLoadingSessions(false));
  }, []);

  const activeSession = sessions.find((s) => s.id === activeSessionId);

  const loadMessagesForSession = useCallback(async (id: string) => {
    const session = sessions.find((item) => item.id === id);
    if (!session || session.messages.length > 0) return;
    try {
      const messagePage = await listMessages(id);
      setSessions((prev) =>
        prev.map((item) =>
          item.id === id ? { ...item, messages: messagePage.items.map(toAIMessage) } : item,
        ),
      );
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tải nội dung cuộc trò chuyện.');
    }
  }, [sessions]);

  useEffect(() => {
    if (activeSessionId) void loadMessagesForSession(activeSessionId);
  }, [activeSessionId, loadMessagesForSession]);

  const handleSelectSession = (id: string) => setActiveSessionId(id);

  const handleNewSession = async () => {
    try {
      const conversation = await createConversation('Điều tra bảo mật mới');
      setSessions((prev) => [toChatSession(conversation), ...prev]);
      setActiveSessionId(conversation.id);
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Không thể tạo cuộc trò chuyện mới.');
    }
  };

  const handleDeleteSession = async (id: string) => {
    try {
      await deleteConversation(id);
      const remaining = sessions.filter((s) => s.id !== id);
      setSessions(remaining);
      if (activeSessionId === id) {
        setActiveSessionId(remaining.length > 0 ? remaining[0].id : '');
      }
    } catch (err) {
      setErrorMsg(err instanceof ApiError ? err.message : 'Không thể xóa cuộc trò chuyện này.');
    }
  };

  const handleSendMessage = useCallback(
    async (text: string, mode: 'fast' | 'deep') => {
      setErrorMsg(null);
      setIsGenerating(true);
      const controller = new AbortController();
      abortControllerRef.current = controller;

      const optimisticUserMessage: AIMessage = {
        id: `pending-${Date.now()}`,
        sender: 'user',
        content: text,
        timestamp: new Date().toISOString(),
      };

      const conversationIdBeforeSend = activeSession?.id;
      if (conversationIdBeforeSend) {
        setSessions((prev) =>
          prev.map((s) =>
            s.id === conversationIdBeforeSend
              ? { ...s, messages: [...s.messages, optimisticUserMessage] }
              : s,
          ),
        );
      }

      try {
        const response = await sendChatMessage({
          message: text,
          conversationId: conversationIdBeforeSend,
          mode,
          signal: controller.signal,
        });

        const assistantMessage: AIMessage = {
          id: response.message_id,
          sender: 'assistant',
          content: response.content,
          timestamp: response.created_at,
          provider: response.provider ?? undefined,
          mode,
          citations: response.citations,
          grounded: response.metadata?.grounded === true,
        };

        setSessions((prev) => {
          const exists = prev.some((s) => s.id === response.conversation_id);
          if (!exists) {
            // First message of a brand-new conversation.
            const newSession: ChatSession = {
              id: response.conversation_id,
              title: text.slice(0, 60),
              updated_at: response.created_at,
              messages: [optimisticUserMessage, assistantMessage],
            };
            return [newSession, ...prev];
          }
          return prev.map((s) =>
            s.id === response.conversation_id
              ? { ...s, messages: [...s.messages, assistantMessage], updated_at: response.created_at }
              : s,
          );
        });
        setActiveSessionId(response.conversation_id);
      } catch (err) {
        if (err instanceof DOMException && err.name === 'AbortError') {
          setErrorMsg('Đã dừng yêu cầu đang chạy.');
          if (conversationIdBeforeSend) {
            setSessions((prev) =>
              prev.map((s) =>
                s.id === conversationIdBeforeSend
                  ? { ...s, messages: s.messages.filter((m) => m.id !== optimisticUserMessage.id) }
                  : s,
              ),
            );
          }
          return;
        }
        setErrorMsg(err instanceof ApiError ? err.message : 'Trợ lý hiện không thể phản hồi.');
        if (conversationIdBeforeSend) {
          setSessions((prev) =>
            prev.map((s) =>
              s.id === conversationIdBeforeSend
                ? { ...s, messages: s.messages.filter((m) => m.id !== optimisticUserMessage.id) }
                : s,
            ),
          );
        }
      } finally {
        setIsGenerating(false);
        if (abortControllerRef.current === controller) {
          abortControllerRef.current = null;
        }
      }
    },
    [activeSession],
  );

  const handleStopGenerating = () => {
    abortControllerRef.current?.abort();
    setIsGenerating(false);
  };

  return (
    <div className="flex-1 flex flex-col h-[calc(100vh-4rem-4px)] overflow-hidden font-body">

      <div className="bg-surface-container border-b border-surface-container-highest px-4 py-2 flex items-center justify-between flex-wrap gap-2 text-xs">
        <div className="flex items-center gap-3">
          <button 
            onClick={() => setIsSidebarOpen(!isSidebarOpen)}
            className="p-1 hover:bg-surface-container-highest rounded text-text-muted hover:text-text-primary transition-colors"
            title={isSidebarOpen ? "Đóng thanh bên" : "Mở thanh bên"}
          >
            <PanelLeft className="h-4 w-4" />
          </button>
          <div className="flex items-center gap-1.5 font-mono text-[10px] text-text-muted">
            <Sparkles className="h-4 w-4 text-primary animate-pulse" />
            <span>TRỢ LÝ AN TOÀN THÔNG TIN</span>
          </div>
          <div className="flex items-center gap-1 border-l border-surface-container-highest pl-3">
            <Link to="/ai" className={`flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-bold ${!knowledgeTab ? 'bg-primary/10 text-primary' : 'text-text-secondary hover:text-text-primary'}`}>
              <MessageSquare className="h-3.5 w-3.5" /> Trò chuyện
            </Link>
            <Link to="/ai/knowledge" className={`flex items-center gap-1.5 px-2 py-1 rounded text-[10px] font-bold ${knowledgeTab ? 'bg-primary/10 text-primary' : 'text-text-secondary hover:text-text-primary'}`}>
              <BookOpen className="h-3.5 w-3.5" /> Kho kiến thức
            </Link>
          </div>
        </div>
        {errorMsg && (
          <div className="flex items-center gap-1.5 text-critical text-[10px] font-mono">
            <AlertTriangle className="h-3.5 w-3.5" />
            <span>{errorMsg}</span>
          </div>
        )}
      </div>

      {knowledgeTab ? (
        <div className="flex-1 overflow-auto p-4 md:p-6 bg-background">
          <KnowledgeBaseView />
        </div>
      ) : (
      <div className="flex-1 flex overflow-hidden">

        {isSidebarOpen && (
          <ConversationSidebar
            sessions={sessions}
            activeSessionId={activeSessionId}
            onSelectSession={handleSelectSession}
            onNewSession={handleNewSession}
            onDeleteSession={handleDeleteSession}
          />
        )}

        <div className="flex-1 min-w-0 flex flex-col bg-background">
          {isLoadingSessions ? (
            <div className="flex-1 flex items-center justify-center text-xs font-mono text-text-muted uppercase">
              Đang tải cuộc trò chuyện...
            </div>
          ) : (
            <ConversationArea
              messages={activeSession ? activeSession.messages : []}
              isGenerating={isGenerating}
              onTriggerSuggestedPrompt={(p) => handleSendMessage(p, 'fast')}
              suggestedPrompts={suggestedPrompts}
            />
          )}
          <Composer
            onSendMessage={handleSendMessage}
            isGenerating={isGenerating}
            onStopGenerating={handleStopGenerating}
          />
        </div>

      </div>
      )}

    </div>
  );
};
export default AIAssistantView;
