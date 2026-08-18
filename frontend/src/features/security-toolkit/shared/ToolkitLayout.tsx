import React from 'react';

interface ToolkitLayoutProps {
  title: string;
  subtitle: string;
  children: React.ReactNode;
}

// Sidebar (AppShell) is the single source of navigation for the toolkit
// pages - this layout used to render its own duplicate tab row for the same
// four links, which meant every toolkit page showed navigation twice.
export const ToolkitLayout: React.FC<ToolkitLayoutProps> = ({ title, subtitle, children }) => {
  return (
    <div className="space-y-6">

      {/* Page Header - unique per route, not a generic "Kiểm tra An toàn" label */}
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">{title}</h2>
          <p className="text-xs text-text-secondary">{subtitle}</p>
        </div>
        <div className="text-right text-[10px] font-mono text-text-muted">
          <span>TRẠNG THÁI: SẴN SÀNG</span>
        </div>
      </div>

      <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5 md:p-8">
        {children}
      </div>

    </div>
  );
};
export default ToolkitLayout;
