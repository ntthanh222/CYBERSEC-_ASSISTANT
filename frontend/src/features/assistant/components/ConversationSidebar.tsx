import React, { useState } from 'react';
import type { ChatSession } from '../assistant.types';
import { Plus, Search, MessageSquare, Trash2 } from 'lucide-react';

interface ConversationSidebarProps {
  sessions: ChatSession[];
  activeSessionId: string;
  onSelectSession: (id: string) => void;
  onNewSession: () => void;
  onDeleteSession: (id: string) => void;
}

export const ConversationSidebar: React.FC<ConversationSidebarProps> = ({
  sessions,
  activeSessionId,
  onSelectSession,
  onNewSession,
  onDeleteSession
}) => {
  const [searchTerm, setSearchTerm] = useState('');

  const filteredSessions = sessions.filter(s => 
    s.title.toLowerCase().includes(searchTerm.toLowerCase())
  );

  const renderThreadItem = (s: ChatSession) => {
    const isSelected = s.id === activeSessionId;

    return (
      <div
        key={s.id}
        onClick={() => onSelectSession(s.id)}
        className={`group flex items-center justify-between px-2 py-1.5 rounded-lg cursor-pointer transition-all ${
          isSelected 
            ? 'bg-primary/10 text-primary border-l-2 border-primary pl-1.5' 
            : 'text-text-secondary hover:text-text-primary hover:bg-surface-container-high'
        }`}
      >
        <div className="flex items-center gap-2 min-w-0 flex-1">
          <MessageSquare className={`h-4 w-4 shrink-0 ${isSelected ? 'text-primary' : 'text-text-muted'}`} />
          <div className="truncate">
            <span className="text-xs font-medium block leading-none truncate">{s.title}</span>
            <span className="text-[9px] text-text-muted block mt-1 font-mono">
              {s.messages.length > 0 ? `${s.messages.length} tin nhắn` : 'Chưa tải nội dung'}
            </span>
          </div>
        </div>

        <div className="flex items-center gap-1.5 shrink-0 ml-2 opacity-0 group-hover:opacity-100 group-focus-within:opacity-100 focus-within:opacity-100">
          <button
            onClick={(e) => { e.stopPropagation(); onDeleteSession(s.id); }}
            className="p-0.5 hover:bg-surface-container-highest rounded text-text-muted hover:text-critical"
            title="Xóa cuộc trò chuyện"
          >
            <Trash2 className="h-3 w-3" />
          </button>
        </div>
      </div>
    );
  };

  return (
    <div className="w-64 border-r border-surface-container-highest/60 bg-surface-container-low hidden md:flex flex-col p-3 shrink-0 h-[calc(100vh-4rem-4px)] select-none">
      
      {/* New Investigation Button */}
      <button 
        onClick={onNewSession}
        className="w-full flex items-center justify-center gap-2 bg-surface-container-high border border-surface-container-highest hover:bg-surface-container-highest text-text-primary font-headline font-bold text-xs py-1.5 rounded-lg transition-colors group mb-3 active:scale-95"
      >
        <Plus className="h-4 w-4 text-primary group-hover:rotate-90 transition-transform duration-200" />
        <span>Cuộc trò chuyện bảo mật mới</span>
      </button>

      {/* Search History */}
      <div className="relative flex items-center mb-3">
        <Search className="h-3.5 w-3.5 absolute left-3 text-text-muted pointer-events-none" />
        <input 
          type="text"
          placeholder="Tìm trong lịch sử..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="w-full bg-background border border-surface-container-highest rounded-lg py-1.5 pl-8 pr-3 text-[10px] font-mono text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/30 transition-all"
        />
      </div>

      {/* List Threads */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1">
        
        {/* Recent Chats */}
        <div className="space-y-1">
          <h4 className="px-2 text-[9px] font-mono tracking-widest text-text-muted uppercase font-bold">
            Nhật ký gần đây
          </h4>
          <div className="space-y-0.5">
            {filteredSessions.length > 0 ? (
              filteredSessions.map(renderThreadItem)
            ) : (
              <span className="text-[10px] text-text-muted italic px-2 block pt-2">Không tìm thấy cuộc trò chuyện phù hợp.</span>
            )}
          </div>
        </div>

      </div>

    </div>
  );
};
