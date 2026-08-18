import React, { useState, useRef, useEffect } from 'react';
import { Send, Square, AlertTriangle } from 'lucide-react';

interface ComposerProps {
  onSendMessage: (text: string, mode: 'fast' | 'deep') => void;
  isGenerating: boolean;
  onStopGenerating: () => void;
}

// Persisted so an in-progress message survives a network/backend outage
// that redirects to /offline and back (the component unmounts/remounts
// across that navigation, which would otherwise lose local state) - never
// auto-sent, only restored into the input box for the user to send
// themselves.
const DRAFT_STORAGE_KEY = 'cybersec_composer_draft';

export const Composer: React.FC<ComposerProps> = ({
  onSendMessage,
  isGenerating,
  onStopGenerating
}) => {
  const [inputText, setInputText] = useState(() => {
    try {
      return sessionStorage.getItem(DRAFT_STORAGE_KEY) ?? '';
    } catch {
      return '';
    }
  });
  const [mode, setMode] = useState<'fast' | 'deep'>('fast');
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    try {
      if (inputText) {
        sessionStorage.setItem(DRAFT_STORAGE_KEY, inputText);
      } else {
        sessionStorage.removeItem(DRAFT_STORAGE_KEY);
      }
    } catch {
      // sessionStorage unavailable (private browsing, quota) - draft
      // preservation degrades gracefully to in-memory-only.
    }
  }, [inputText]);

  // Auto-resize textarea height as typing
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 180)}px`;
    }
  }, [inputText]);

  const handleSend = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputText.trim()) return;

    if (isGenerating) {
      onStopGenerating();
    } else {
      onSendMessage(inputText.trim(), mode);
      setInputText('');
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend(e);
    }
  };

  return (
    <form 
      onSubmit={handleSend}
      className="p-3 border-t border-surface-container-highest bg-surface-container-low/80 backdrop-blur shrink-0 relative"
    >
      
      {/* Sensitive warning banner */}
      <div className="absolute -top-7 left-0 w-full flex items-center gap-1.5 text-[9px] text-text-muted font-mono justify-center">
        <AlertTriangle className="h-3 w-3 text-warning shrink-0" />
        <span>CHÍNH SÁCH DỮ LIỆU NHẠY CẢM: KHÔNG DÁN SSH KEY, ACCESS TOKEN HOẶC MẬT KHẨU MÃ HÓA THẬT VÀO ĐÂY.</span>
      </div>

      {/* Input textbox area with inline controls */}
      <div className="relative flex items-end bg-background border border-surface-container-highest rounded-xl p-2 shadow-sm focus-within:ring-1 focus-within:ring-primary/40 focus-within:border-primary/40 transition-all max-w-4xl mx-auto">
        
        {/* Toggle Mode */}
        <div className="flex flex-col justify-end gap-1 shrink-0 mb-1">
          <div className="flex items-center gap-1">
            <button
              type="button"
              onClick={() => setMode('fast')}
              className={`px-2 py-0.5 rounded text-[9px] font-mono font-bold tracking-wider uppercase transition-all ${
                mode === 'fast'
                  ? 'bg-primary/10 text-primary border border-primary/20'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              Fast
            </button>
            <button
              type="button"
              onClick={() => setMode('deep')}
              className={`px-2 py-0.5 rounded text-[9px] font-mono font-bold tracking-wider uppercase transition-all ${
                mode === 'deep'
                  ? 'bg-primary/10 text-primary border border-primary/20'
                  : 'text-text-muted hover:text-text-primary'
              }`}
            >
              Deep
            </button>
          </div>
        </div>

        <textarea
          ref={textareaRef}
          value={inputText}
          onChange={(e) => setInputText(e.target.value)}
          onKeyDown={handleKeyDown}
          rows={1}
          placeholder="Hỏi CyberSec Assistant..."
          className="flex-1 min-w-0 max-h-[180px] bg-transparent border-none py-1.5 px-3 text-sm text-text-primary placeholder:text-text-muted focus:outline-none resize-none"
        />

        {/* Action Send/Stop */}
        <button
          type="submit"
          disabled={!inputText.trim() && !isGenerating}
          className={`h-9 w-9 rounded-lg flex items-center justify-center transition-all shrink-0 ml-1 mb-0.5 ${
            isGenerating 
              ? 'bg-critical text-background hover:bg-critical-dim'
              : 'bg-primary text-background hover:bg-primary-container disabled:opacity-30 disabled:pointer-events-none'
          }`}
          title={isGenerating ? 'Dừng tạo phản hồi' : 'Gửi tin nhắn'}
        >
          {isGenerating ? <Square className="h-4 w-4" /> : <Send className="h-4 w-4" />}
        </button>
      </div>

    </form>
  );
};
