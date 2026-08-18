import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import { LayoutDashboard, List, GitFork, Bookmark } from 'lucide-react';

interface IOCLayoutProps {
  children: React.ReactNode;
}

const TABS = [
  { name: 'Tổng quan', path: '/threat-intelligence', icon: LayoutDashboard, exact: true },
  { name: 'Danh sách IOC', path: '/threat-intelligence/iocs', icon: List, exact: false },
  { name: 'Biểu đồ', path: '/threat-intelligence/graph', icon: GitFork, exact: false },
  { name: 'Danh sách theo dõi', path: '/threat-intelligence/watchlist', icon: Bookmark, exact: false },
];

export const IOCLayout: React.FC<IOCLayoutProps> = ({ children }) => {
  const location = useLocation();

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex justify-between items-center border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">
            Ma Trận Threat Intelligence
          </h2>
          <p className="text-xs text-text-secondary">
            Theo dõi IOC, biểu đồ quan hệ, và giám sát danh sách theo dõi đang hoạt động.
          </p>
        </div>
        <div className="text-right text-[10px] font-mono text-text-muted">
          <span>TRẠNG THÁI NGUỒN DỮ LIỆU</span>
          <span className="block text-primary">ĐƯỢC HỖ TRỢ BỞI API</span>
        </div>
      </div>

      {/* Tab Navigation */}
      <div className="border-b border-surface-container-highest flex items-center gap-1 overflow-x-auto select-none">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = tab.exact
            ? location.pathname === tab.path
            : location.pathname.startsWith(tab.path);
          return (
            <Link
              key={tab.path}
              to={tab.path}
              className={`flex items-center gap-2 px-4 py-2.5 text-xs font-headline font-bold border-b-2 transition-all shrink-0 ${
                isActive
                  ? 'border-primary text-primary bg-primary/5'
                  : 'border-transparent text-text-secondary hover:text-text-primary hover:bg-surface-container-high/40'
              }`}
            >
              <Icon className="h-4 w-4" />
              <span>{tab.name}</span>
            </Link>
          );
        })}
      </div>

      {/* Content */}
      <div className="bg-surface-container border border-surface-container-highest rounded-xl p-5 md:p-8">
        {children}
      </div>
    </div>
  );
};

export default IOCLayout;
