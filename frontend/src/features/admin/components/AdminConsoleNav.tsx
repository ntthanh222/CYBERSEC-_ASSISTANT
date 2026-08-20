import React from 'react';
import { Link, useLocation } from 'react-router-dom';
import {
  Bot,
  FileText,
  FolderKanban,
  HeartPulse,
  RadioTower,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Timer,
  Users,
} from 'lucide-react';

const tabs = [
  { label: 'Overview', path: '/admin/overview', match: '/admin/overview', icon: ShieldCheck },
  { label: 'Users & Roles', path: '/admin/users', match: '/admin/users', icon: Users },
  { label: 'Audit Logs', path: '/admin/audit', match: '/admin/audit', icon: FileText },
  // Task 7: vuln-lifecycle admin visibility tabs.
  { label: 'Workspaces', path: '/admin/workspaces', match: '/admin/workspaces', icon: FolderKanban },
  { label: 'Projects', path: '/admin/projects', match: '/admin/projects', icon: FolderKanban },
  { label: 'Findings', path: '/admin/findings', match: '/admin/findings', icon: ShieldAlert },
  { label: 'SLA / Policies', path: '/admin/sla-policies', match: '/admin/sla-policies', icon: Timer },
  { label: 'System Health', path: '/admin/health', match: '/admin/health', icon: HeartPulse },
  { label: 'AI & Knowledge', path: '/admin/rag', match: '/admin/rag', icon: Bot },
  { label: 'Crawler', path: '/admin/crawler', match: '/admin/crawler', icon: RadioTower },
  { label: 'Security Settings', path: '/admin/settings', match: '/admin/settings', icon: Settings },
];

export const AdminConsoleNav: React.FC = () => {
  const location = useLocation();

  return (
    <div className="border-b border-surface-container-highest flex items-center gap-1 overflow-x-auto">
      {tabs.map((tab) => {
        const Icon = tab.icon;
        const active = location.pathname.startsWith(tab.match);
        return (
          <Link
            key={tab.path}
            to={tab.path}
            className={`flex items-center gap-2 px-3 py-2.5 text-xs font-bold border-b-2 shrink-0 ${
              active
                ? 'border-primary text-primary bg-primary/5'
                : 'border-transparent text-text-secondary hover:text-text-primary'
            }`}
          >
            <Icon className="h-4 w-4" />
            {tab.label}
          </Link>
        );
      })}
    </div>
  );
};
