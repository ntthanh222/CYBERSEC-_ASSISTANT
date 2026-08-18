import React, { useRef, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import type { AIMessage } from '../../../types/data-provider.types';
import {
  User as UserIcon, Bot, Copy,
  Link as LinkIcon, BookOpen
} from 'lucide-react';

interface ConversationAreaProps {
  messages: AIMessage[];
  isGenerating: boolean;
  onTriggerSuggestedPrompt: (promptText: string) => void;
  suggestedPrompts?: string[];
}

export const ConversationArea: React.FC<ConversationAreaProps> = ({
  messages,
  isGenerating,
  onTriggerSuggestedPrompt,
  suggestedPrompts = []
}) => {
  const scrollRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [messages, isGenerating]);

  const handleCopyText = (text: string) => {
    navigator.clipboard.writeText(text);
  };

  return (
    <div className="flex-1 overflow-y-auto px-4 py-6 space-y-6" ref={scrollRef}>
      
      {/* Empty State */}
      {messages.length === 0 && (
        <div className="h-full flex flex-col items-center justify-center text-center space-y-4 max-w-md mx-auto py-12">
          <div className="h-14 w-14 rounded-full bg-surface-container-high border border-surface-container-highest flex items-center justify-center pulse-mint text-primary">
            <Bot className="h-7 w-7" />
          </div>
          <div className="space-y-1.5">
            <h3 className="font-headline font-bold text-sm text-text-primary">Trò chuyện với CyberSec Assistant</h3>
            <p className="text-xs text-text-secondary leading-relaxed">
              Hỏi đáp về an toàn thông tin, nhờ giải thích kết quả Kiểm tra Website/Mật khẩu/CVE, hoặc xin hướng dẫn xử lý khi nghi ngờ gặp sự cố bảo mật.
            </p>
          </div>

          {/* Quick Prompts Box */}
          {suggestedPrompts.length > 0 && (
            <div className="w-full pt-4 space-y-2">
              <span className="text-[9px] font-mono text-text-muted uppercase tracking-widest block font-bold">Câu hỏi gợi ý</span>
              <div className="space-y-1.5">
                {suggestedPrompts.map((p, idx) => (
                  <button
                    key={idx}
                    onClick={() => onTriggerSuggestedPrompt(p)}
                    className="w-full text-left bg-surface-container hover:bg-surface-container-high border border-surface-container-highest hover:border-primary/20 p-2.5 rounded-lg text-[11px] text-text-secondary hover:text-text-primary transition-all font-mono truncate"
                  >
                    {p}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Render messages list */}
      {messages.map((msg) => {
        const isUser = msg.sender === 'user';
        return (
          <div 
            key={msg.id}
            className={`flex gap-4 w-full max-w-4xl ${isUser ? 'ml-auto flex-row-reverse' : 'mr-auto'}`}
          >
            
            {/* Avatar */}
            <div className={`h-8 w-8 rounded-full flex items-center justify-center border shrink-0 ${
              isUser 
                ? 'bg-surface-container-high border-surface-container-highest text-text-secondary' 
                : 'bg-primary/10 border-primary/20 text-primary'
            }`}>
              {isUser ? <UserIcon className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
            </div>

            {/* Bubble */}
            <div className="space-y-2">

              <div className={`p-4 rounded-xl border ${
                isUser
                  ? 'bg-surface-container-high border-surface-container-highest text-text-primary'
                  : 'bg-surface-container border-surface-container-highest text-text-secondary space-y-4'
              }`}>

                {/* Text Content */}
                <div className="text-sm leading-relaxed whitespace-pre-wrap select-text">
                  {msg.content}
                </div>

                {/* Additional metadata for Assistant replies */}
                {!isUser && (
                  <div className="space-y-4 border-t border-surface-container-highest pt-4">
                    
                    {/* Metrics row */}
                    {msg.provider && (
                      <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-[9px] font-mono text-text-muted">
                        <div>
                          <span>PROVIDER: </span>
                          <span className="text-text-primary font-bold">{msg.provider}</span>
                        </div>
                        {msg.confidence !== undefined && (
                          <div>
                            <span>CONFIDENCE: </span>
                            <span className="text-primary font-bold">{(msg.confidence * 100).toFixed(0)}%</span>
                          </div>
                        )}
                        {msg.mode && (
                          <div>
                            <span>MODE: </span>
                            <span className="text-info font-bold uppercase">{msg.mode}</span>
                          </div>
                        )}
                      </div>
                    )}

                    {/* Knowledge-base citations (Phase 2.6 RAG) */}
                    {msg.citations && msg.citations.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[8px] font-mono text-text-muted uppercase tracking-widest font-bold">
                          Trích dẫn:
                        </span>
                        {msg.citations.map((citation) => (
                          <button
                            key={`${citation.chunk_id}-${citation.marker}`}
                            onClick={() =>
                              citation.document_id &&
                              navigate(`/knowledge-base/documents/${citation.document_id}`)
                            }
                            disabled={!citation.document_id}
                            className="flex items-center gap-1 bg-background border border-surface-container-highest hover:border-primary/40 px-2 py-0.5 rounded text-[9px] font-mono disabled:cursor-default disabled:hover:border-surface-container-highest"
                            title={`Độ tương đồng ${(citation.score * 100).toFixed(0)}%`}
                          >
                            <BookOpen className="h-3 w-3 text-primary shrink-0" />
                            <span className="text-text-secondary truncate">
                              [{citation.marker}] {citation.title}
                              {citation.page ? ` · p.${citation.page}` : ''}
                              {citation.heading ? ` · ${citation.heading}` : ''}
                            </span>
                          </button>
                        ))}
                      </div>
                    )}
                    {!isUser && msg.grounded === false && msg.citations !== undefined && (
                      <div className="text-[9px] font-mono text-warning">
                        Không dựa trên Knowledge Base - câu trả lời từ kiến thức chung.
                      </div>
                    )}

                    {/* Sources citation Chips */}
                    {msg.sources && msg.sources.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[8px] font-mono text-text-muted uppercase tracking-widest font-bold">Nguồn:</span>
                        {msg.sources.map((src: string, sIdx: number) => (
                          <div 
                            key={sIdx}
                            className="flex items-center gap-1 bg-background border border-surface-container-highest px-2 py-0.5 rounded text-[9px] font-mono"
                          >
                            <LinkIcon className="h-3 w-3 text-text-muted shrink-0" />
                            <span className="text-text-secondary">{src}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* MITRE ATT&CK Matrix links */}
                    {msg.mitre_techniques && msg.mitre_techniques.length > 0 && (
                      <div className="flex flex-wrap items-center gap-1.5">
                        <span className="text-[8px] font-mono text-text-muted uppercase tracking-widest font-bold">MITRE:</span>
                        {msg.mitre_techniques.map((tech: string, tIdx: number) => (
                          <div 
                            key={tIdx} 
                            className="flex items-center gap-1.5 bg-critical/5 border border-critical/20 px-2 py-0.5 rounded text-[9px] font-mono"
                          >
                            <span className="h-1.5 w-1.5 bg-critical rounded-full" />
                            <span className="text-critical font-bold">{tech}</span>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Actions panel */}
                    <div className="flex flex-wrap items-center gap-3 pt-1 border-t border-surface-container-highest/40">
                      
                      {/* Copy button */}
                      <div className="flex items-center gap-1.5">
                        <button 
                          onClick={() => handleCopyText(msg.content)}
                          className="p-1 hover:bg-surface-container-high rounded text-text-muted hover:text-text-primary"
                          title="Sao chép tin nhắn"
                        >
                          <Copy className="h-3.5 w-3.5" />
                        </button>
                      </div>

                    </div>

                  </div>
                )}

              </div>

              {/* Timestamp details */}
              <div className={`text-[9px] font-mono text-text-muted ${isUser ? 'text-right' : 'text-left'}`}>
                <span>{new Date(msg.timestamp).toLocaleTimeString()}</span>
              </div>

            </div>

          </div>
        );
      })}

      {/* Generating thinking indicator */}
      {isGenerating && (
        <div className="flex gap-4 max-w-[85%] mr-auto">
          <div className="h-8 w-8 rounded-full bg-primary/10 border border-primary/20 flex items-center justify-center text-primary shrink-0 pulse-mint">
            <Bot className="h-4 w-4" />
          </div>
          <div className="bg-surface-container border border-surface-container-highest rounded-xl p-4 flex items-center gap-2">
            <div className="flex gap-1">
              <span className="h-1.5 w-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '0ms' }} />
              <span className="h-1.5 w-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '150ms' }} />
              <span className="h-1.5 w-1.5 bg-primary rounded-full animate-bounce" style={{ animationDelay: '300ms' }} />
            </div>
            <span className="text-[10px] font-mono text-text-muted uppercase tracking-wider pl-1">Đang tạo phản hồi...</span>
          </div>
        </div>
      )}

    </div>
  );
};
