import React, { useState, useEffect, useRef } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import { useAuth } from '../features/auth/AuthContext';
import { getSystemHealth } from '../lib/api/system';
import { listNotifications, type NotificationRecord } from '../lib/api/notifications';
import type { ServiceStatus } from '../types/data-provider.types';
import {
  Menu, X, Bell, Search, User as UserIcon, LogOut, Shield,
  LayoutDashboard, BrainCircuit, Settings, ChevronDown,
  Globe, KeyRound, FileSearch, Newspaper, History as HistoryIcon,
  FolderKanban, ClipboardList,
} from 'lucide-react';

interface AppShellProps {
  children: React.ReactNode;
}

export const AppShell: React.FC<AppShellProps> = ({ children }) => {
  const { user, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [healthStatus, setHealthStatus] = useState<ServiceStatus[]>([]);
  const [notifDropdownOpen, setNotifDropdownOpen] = useState(false);
  const [recentNotifications, setRecentNotifications] = useState<NotificationRecord[]>([]);
  const [unreadNotifCount, setUnreadNotifCount] = useState(0);
  const [profileDropdownOpen, setProfileDropdownOpen] = useState(false);
  
  const notifRef = useRef<HTMLDivElement>(null);
  const profileRef = useRef<HTMLDivElement>(null);
  const sidebarRef = useRef<HTMLDivElement>(null);

  // Close dropdowns on outside click
  useEffect(() => {
    const handleOutsideClick = (e: MouseEvent) => {
      if (notifRef.current && !notifRef.current.contains(e.target as Node)) {
        setNotifDropdownOpen(false);
      }
      if (profileRef.current && !profileRef.current.contains(e.target as Node)) {
        setProfileDropdownOpen(false);
      }
    };
    document.addEventListener('mousedown', handleOutsideClick);
    return () => document.removeEventListener('mousedown', handleOutsideClick);
  }, []);

  // Fetch real backend/database/redis/migration/pgvector/local-auth readiness
  useEffect(() => {
    let cancelled = false;

    const refresh = () => {
      getSystemHealth()
        .then((res) => {
          if (cancelled) return;
          const entries = Object.entries(res.checks).map(([name, check]) => ({
            name,
            status: check.status,
            latency: check.latency_ms ?? 0,
          }));
          setHealthStatus(entries);
        })
        .catch(() => {
          if (cancelled) return;
          setHealthStatus([{ name: 'backend', status: 'unavailable', latency: 0 }]);
        });
    };

    refresh();
    const interval = window.setInterval(refresh, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  // Fetch real notification records for the header dropdown/badge
  useEffect(() => {
    let cancelled = false;
    const refreshNotifications = () => {
      listNotifications(true)
        .then((page) => {
          if (cancelled) return;
          setRecentNotifications(page.items.slice(0, 5));
          setUnreadNotifCount(page.unread_count);
        })
        .catch(() => {
          if (cancelled) return;
          setRecentNotifications([]);
          setUnreadNotifCount(0);
        });
    };
    refreshNotifications();
    const interval = window.setInterval(refreshNotifications, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  // Close mobile sidebar on escape key
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, []);

  // Determine system overall health state
  const isHealthy = healthStatus.every(s => s.status === 'healthy');
  const isDegraded = healthStatus.some(s => s.status === 'degraded' || s.status === 'unavailable');

  const navigationGroups = [
    {
      title: 'Tổng quan',
      items: [
        { name: 'Dashboard', path: '/dashboard', icon: LayoutDashboard },
        { name: 'AI Assistant', path: '/ai', icon: BrainCircuit },
        { name: 'Dự án', path: '/projects', icon: FolderKanban },
        { name: 'Công việc của tôi', path: '/my-tasks', icon: ClipboardList },
      ]
    },
    {
      title: 'Kiểm tra an toàn',
      items: [
        { name: 'Kiểm tra Website', path: '/toolkit/url-scanner', icon: Globe },
        { name: 'Kiểm tra Mật khẩu', path: '/toolkit/password-checker', icon: KeyRound },
        { name: 'Tra cứu CVE', path: '/toolkit/cve-lookup', icon: FileSearch },
      ]
    },
    {
      title: 'Thông tin',
      items: [
        { name: 'Tin tức Bảo mật', path: '/news', icon: Newspaper },
        { name: 'Lịch sử Kiểm tra', path: '/toolkit/history', icon: HistoryIcon },
      ]
    }
  ];

  // If user is admin/super_admin, append Admin settings Group
  const isAdmin = user && (user.role === 'admin' || user.role === 'super_admin');
  
  const handleLogout = () => {
    logout();
    navigate('/login');
  };

  const isActive = (path: string) => {
    if (path === '/ai') {
      return location.pathname.startsWith('/ai') || location.pathname.startsWith('/knowledge-base');
    }
    if (path === '/news') {
      return location.pathname.startsWith('/news');
    }
    // Toolkit sub-tabs (website/password/cve/history) share the /toolkit
    // prefix — match the exact sub-path so only the clicked tab highlights.
    return location.pathname === path || location.pathname.startsWith(`${path}/`);
  };

  return (
    <div className="min-h-screen bg-background text-text-primary flex flex-col font-body">
      
      {/* Top Header Bar */}
      <header className="h-16 border-b border-surface-container-highest bg-surface/80 backdrop-blur-md sticky top-0 z-40 flex items-center justify-between px-4 md:px-8">
        
        {/* Logo & Mobile Menu Toggle */}
        <div className="flex items-center gap-3">
          <button 
            className="md:hidden p-1.5 hover:bg-surface-container-high rounded-md text-text-secondary focus:outline-none focus:ring-1 focus:ring-primary/40"
            onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
            aria-label="Chuyển đổi menu điều hướng"
            aria-expanded={mobileMenuOpen}
          >
            <Menu className="h-6 w-6" />
          </button>
          
          <div className="flex items-center gap-2">
            <div className="h-8 w-8 rounded bg-primary/20 flex items-center justify-center border border-primary/40 pulse-mint">
              <Shield className="h-4 w-4 text-primary" />
            </div>
            <div>
              <span className="font-headline font-bold tracking-tight text-text-primary block leading-none">CyberSec Assistant</span>
              <span className="text-[10px] text-text-muted font-mono tracking-wider uppercase">Security Console</span>
            </div>
          </div>
        </div>

        {/* Global Search (Figma style) */}
        <div className="hidden md:flex items-center flex-1 max-w-md mx-8 relative">
          <Search className="h-4 w-4 absolute left-3 text-text-muted pointer-events-none" />
          <input 
            type="text" 
            placeholder="Tìm trong kho lưu trữ mối đe dọa (Ctrl+K)..."
            className="w-full bg-surface-container-low border border-surface-container-highest rounded-lg py-1.5 pl-9 pr-4 text-xs font-mono tracking-wider text-text-primary placeholder:text-text-muted focus:outline-none focus:ring-1 focus:ring-primary/40 focus:border-primary/40 transition-all"
            onClick={() => navigate('/notifications?pallete=true')}
          />
        </div>

        {/* Action Controls */}
        <div className="flex min-w-0 items-center gap-2 sm:gap-4">
          
          {/* Live readiness indicator, backed by GET /api/system/health */}
          <div 
            className="hidden lg:flex items-center gap-2 bg-surface-container-low border border-surface-container-highest px-3 py-1 rounded-md cursor-pointer hover:bg-surface-container-high transition-colors"
            onClick={() => navigate('/admin/health')}
            title="Trạng thái kiểm tra hệ thống"
          >
            <span className={`h-2.5 w-2.5 rounded-full ${isHealthy ? 'bg-success' : isDegraded ? 'bg-warning' : 'bg-critical'} pulse-mint`} />
            <span className="text-[10px] font-mono tracking-widest text-text-secondary uppercase">
              {isHealthy ? 'HỆ THỐNG ỔN ĐỊNH' : 'HỆ THỐNG SUY GIẢM'}
            </span>
          </div>

          {/* Notifications Dropdown Toggle */}
          <div className="relative" ref={notifRef}>
            <button 
              className="p-1.5 hover:bg-surface-container-high rounded-full text-text-secondary hover:text-text-primary relative transition-colors focus:outline-none focus:ring-1 focus:ring-primary/40"
              onClick={() => setNotifDropdownOpen(!notifDropdownOpen)}
              aria-label="Mở danh sách thông báo"
            >
              <Bell className="h-5 w-5" />
              {unreadNotifCount > 0 && (
                <span className="absolute top-1 right-1 h-2 w-2 bg-critical rounded-full" />
              )}
            </button>

            {notifDropdownOpen && (
              <div className="absolute right-0 mt-2 w-80 bg-surface-container-high border border-surface-container-highest rounded-lg shadow-elevated z-50 p-2 font-body">
                <div className="flex justify-between items-center px-3 py-2 border-b border-surface-container-highest">
                  <span className="font-headline font-bold text-xs">
                    {unreadNotifCount > 0 ? `${unreadNotifCount} thông báo chưa đọc` : 'Thông báo'}
                  </span>
                  <Link to="/notifications" className="text-[10px] text-primary hover:underline" onClick={() => setNotifDropdownOpen(false)}>Xem tất cả</Link>
                </div>
                <div className="max-h-60 overflow-y-auto mt-1 space-y-1">
                  {recentNotifications.length === 0 ? (
                    <p className="text-[10px] text-text-muted text-center py-4">Không có thông báo chưa đọc.</p>
                  ) : (
                    recentNotifications.map((notification) => (
                      <div
                        key={notification.id}
                        className={`p-3 hover:bg-surface-container-highest rounded-md border-l-2 ${
                          notification.severity === 'critical'
                            ? 'border-critical'
                            : notification.severity === 'warning'
                              ? 'border-warning'
                              : 'border-primary'
                        }`}
                      >
                        <p className="text-xs font-bold text-text-primary">{notification.title}</p>
                        {notification.body && (
                          <p className="text-[10px] text-text-secondary mt-0.5 truncate">{notification.body}</p>
                        )}
                        <p className="text-[9px] text-text-muted mt-1 font-mono">
                          {new Date(notification.created_at).toLocaleTimeString()} • {notification.severity}
                        </p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            )}
          </div>

          {/* Profile Dropdown Toggle */}
          <div className="relative min-w-0 border-l border-surface-container-highest pl-2 sm:pl-4" ref={profileRef}>
            <button 
              className="flex min-w-0 max-w-[42vw] items-center gap-2 hover:opacity-80 focus:outline-none sm:max-w-[260px] lg:max-w-[320px]"
              onClick={() => setProfileDropdownOpen(!profileDropdownOpen)}
              title={user ? `${user.username} - ${user.role}` : 'Khách'}
              aria-label="Tùy chọn hồ sơ người dùng"
            >
              <div className="h-8 w-8 shrink-0 rounded-full bg-surface-container-high border border-primary/20 flex items-center justify-center font-mono font-bold text-primary text-xs">
                {user ? user.username.substring(0, 2).toUpperCase() : 'AN'}
              </div>
              <div className="hidden min-w-0 overflow-hidden text-left sm:block [&>span:first-child]:block [&>span:first-child]:truncate">
                <span className="text-xs font-bold text-text-primary block leading-none">{user ? user.username : 'Khách'}</span>
                <span className="text-[9px] text-primary font-mono tracking-wider leading-none block mt-0.5 uppercase">
                  {user ? user.role.replace('_', ' ') : 'Chưa xác thực'}
                </span>
              </div>
              <ChevronDown className="h-3 w-3 shrink-0 text-text-muted hidden sm:block" />
            </button>

            {profileDropdownOpen && (
              <div className="absolute right-0 mt-2 w-48 bg-surface-container-high border border-surface-container-highest rounded-lg shadow-elevated z-50 p-1">
                <Link 
                  to="/profile" 
                  className="flex items-center gap-2 px-3 py-2 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-container-highest rounded-md transition-colors"
                  onClick={() => setProfileDropdownOpen(false)}
                >
                  <UserIcon className="h-4 w-4" />
                  <span>Hồ sơ của tôi</span>
                </Link>
                {isAdmin && (
                  <Link 
                    to="/admin/users" 
                    className="flex items-center gap-2 px-3 py-2 text-xs text-text-secondary hover:text-text-primary hover:bg-surface-container-highest rounded-md transition-colors"
                    onClick={() => setProfileDropdownOpen(false)}
                  >
                    <Settings className="h-4 w-4" />
                    <span>Khu vực quản trị</span>
                  </Link>
                )}
                <div className="border-t border-surface-container-highest my-1"></div>
                <button 
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs text-critical hover:bg-critical/10 rounded-md transition-colors text-left"
                  onClick={handleLogout}
                >
                  <LogOut className="h-4 w-4" />
                  <span>Đăng xuất</span>
                </button>
              </div>
            )}
          </div>

        </div>
      </header>

      {/* Main Container */}
      <div className="flex-1 flex overflow-hidden">
        
        {/* Desktop Sidebar Navigation */}
        <aside className="w-64 border-r border-surface-container-highest bg-surface-container-low hidden md:flex flex-col p-4 overflow-y-auto select-none">
          <div className="space-y-6">
            {navigationGroups.map((group, gIdx) => (
              <div key={gIdx} className="space-y-1">
                <h3 className="px-3 text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">{group.title}</h3>
                <nav className="space-y-0.5">
                  {group.items.map((item, iIdx) => {
                    const Icon = item.icon;
                    const active = isActive(item.path);
                    return (
                      <Link 
                        key={iIdx} 
                        to={item.path}
                        className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                          active 
                            ? 'bg-primary/10 text-primary border-l-2 border-primary pl-2' 
                            : 'text-text-secondary hover:text-text-primary hover:bg-surface-container-high'
                        }`}
                      >
                        <Icon className={`h-4 w-4 ${active ? 'text-primary' : 'text-text-muted'}`} />
                        <span>{item.name}</span>
                      </Link>
                    );
                  })}
                </nav>
              </div>
            ))}

            {/* Admin Management Section */}
            {isAdmin && (
              <div className="space-y-1 pt-2 border-t border-surface-container-highest/40">
                <h3 className="px-3 text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Quản trị</h3>
                <nav className="space-y-0.5">
                  <Link 
                    to="/admin/users"
                    className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium transition-all ${
                      location.pathname.startsWith('/admin') 
                        ? 'bg-primary/10 text-primary border-l-2 border-primary pl-2' 
                        : 'text-text-secondary hover:text-text-primary hover:bg-surface-container-high'
                    }`}
                  >
                    <Settings className={`h-4 w-4 ${location.pathname.startsWith('/admin') ? 'text-primary' : 'text-text-muted'}`} />
                    <span>Control Console</span>
                  </Link>
                </nav>
              </div>
            )}
          </div>
          
          <div className="mt-auto pt-8 px-3 border-t border-surface-container-highest/20 text-center">
            <span className="text-[10px] font-mono text-text-muted block">CYBERSEC ASSISTANT BẢO MẬT</span>
            <span className="text-[9px] font-mono text-primary mt-1 block">MÃ HÓA SSL</span>
          </div>
        </aside>

        {/* Mobile Sidebar Slide Drawer */}
        {mobileMenuOpen && (
          <div 
            className="fixed inset-0 bg-black/60 backdrop-blur-sm z-50 md:hidden"
            onClick={() => setMobileMenuOpen(false)}
          >
            <div 
              ref={sidebarRef}
              className="w-64 h-full bg-surface-container-low border-r border-surface-container-highest flex flex-col p-4 overflow-y-auto"
              onClick={(e) => e.stopPropagation()}
            >
              <div className="flex justify-between items-center mb-6">
                <span className="font-headline font-bold text-sm text-primary">ĐIỀU HƯỚNG</span>
                <button
                  className="p-1 hover:bg-surface-container-high rounded text-text-secondary"
                  onClick={() => setMobileMenuOpen(false)}
                  aria-label="Đóng ngăn điều hướng"
                >
                  <X className="h-5 w-5" />
                </button>
              </div>

              <div className="space-y-6">
                {navigationGroups.map((group, gIdx) => (
                  <div key={gIdx} className="space-y-1">
                    <h3 className="px-3 text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">{group.title}</h3>
                    <nav className="space-y-0.5">
                      {group.items.map((item, iIdx) => {
                        const Icon = item.icon;
                        const active = isActive(item.path);
                        return (
                          <Link 
                            key={iIdx} 
                            to={item.path}
                            className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium ${
                              active 
                                ? 'bg-primary/10 text-primary border-l-2 border-primary pl-2' 
                                : 'text-text-secondary hover:text-text-primary hover:bg-surface-container-high'
                            }`}
                            onClick={() => setMobileMenuOpen(false)}
                          >
                            <Icon className={`h-4 w-4 ${active ? 'text-primary' : 'text-text-muted'}`} />
                            <span>{item.name}</span>
                          </Link>
                        );
                      })}
                    </nav>
                  </div>
                ))}

                {/* Admin Management Section */}
                {isAdmin && (
                  <div className="space-y-1 pt-2 border-t border-surface-container-highest/40">
                    <h3 className="px-3 text-[10px] font-mono tracking-widest text-text-muted uppercase font-bold">Quản trị</h3>
                    <nav className="space-y-0.5">
                      <Link 
                        to="/admin/users"
                        className={`flex items-center gap-3 px-3 py-2 rounded-lg text-xs font-medium ${
                          location.pathname.startsWith('/admin') 
                            ? 'bg-primary/10 text-primary border-l-2 border-primary pl-2' 
                            : 'text-text-secondary hover:text-text-primary hover:bg-surface-container-high'
                        }`}
                        onClick={() => setMobileMenuOpen(false)}
                      >
                        <Settings className="h-4 w-4 text-text-muted" />
                        <span>Control Console</span>
                      </Link>
                    </nav>
                  </div>
                )}
              </div>
            </div>
          </div>
        )}

        {/* Main Content Area */}
        <main className="flex-1 overflow-y-auto p-4 md:p-8 bg-background relative">
          <div className="max-w-[1600px] mx-auto space-y-8">
            {children}
          </div>
        </main>

      </div>
    </div>
  );
};
