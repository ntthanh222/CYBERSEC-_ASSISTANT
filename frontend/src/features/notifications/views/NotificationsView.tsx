import React, { useCallback, useEffect, useState } from 'react';
import { AlertTriangle, Bell, BellOff, CheckCheck, RefreshCw } from 'lucide-react';
import {
  listNotifications,
  setNotificationRead,
  type NotificationRecord,
} from '../../../lib/api/notifications';

const SEVERITY_STYLES: Record<string, string> = {
  info: 'text-primary border-primary/30 bg-primary/10',
  warning: 'text-warning border-warning/30 bg-warning/10',
  critical: 'text-critical border-critical/30 bg-critical/10',
};

export const NotificationsView: React.FC = () => {
  const [items, setItems] = useState<NotificationRecord[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [unreadOnly, setUnreadOnly] = useState(false);
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(() => {
    setIsLoading(true);
    setError('');
    listNotifications(unreadOnly)
      .then((page) => {
        setItems(page.items);
        setUnreadCount(page.unread_count);
      })
      .catch((err) => setError(err instanceof Error ? err.message : 'Unable to load notifications.'))
      .finally(() => setIsLoading(false));
  }, [unreadOnly]);

  useEffect(load, [load]);

  const markRead = async (notification: NotificationRecord, isRead: boolean) => {
    try {
      await setNotificationRead(notification.id, isRead);
      load();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to update notification.');
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between border-b border-surface-container-highest/60 pb-4">
        <div>
          <h2 className="font-headline font-black text-2xl tracking-tight text-text-primary">
            Notification Center
          </h2>
          <p className="text-xs text-text-secondary">
            {unreadCount > 0 ? `${unreadCount} unread` : 'All caught up'}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setUnreadOnly((v) => !v)}
            className={`flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold border transition-all ${
              unreadOnly
                ? 'bg-primary/10 border-primary/30 text-primary'
                : 'bg-surface-container border-surface-container-highest text-text-secondary'
            }`}
          >
            <BellOff className="h-3.5 w-3.5" />
            Unread only
          </button>
          <button
            onClick={load}
            disabled={isLoading}
            className="flex items-center gap-1.5 px-3 py-2 rounded-lg text-xs font-bold border bg-surface-container border-surface-container-highest text-text-secondary disabled:opacity-50"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isLoading ? 'animate-spin' : ''}`} />
            Refresh
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center justify-between gap-2 rounded-lg border border-critical/30 bg-critical/10 p-3 text-xs text-critical">
          <span className="flex items-center gap-2">
            <AlertTriangle className="h-4 w-4" />
            {error}
          </span>
          <button onClick={load} className="font-bold underline">
            Retry
          </button>
        </div>
      )}

      {isLoading && !error && (
        <div className="text-xs text-text-muted font-mono" role="status">
          Loading notifications...
        </div>
      )}

      {!isLoading && !error && items.length === 0 && (
        <div className="flex flex-col items-center justify-center gap-2 py-16 text-center bg-surface-container border border-surface-container-highest rounded-lg">
          <Bell className="h-8 w-8 text-text-muted" />
          <p className="text-sm text-text-secondary">
            {unreadOnly ? 'No unread notifications.' : 'No notifications yet.'}
          </p>
        </div>
      )}

      <ul className="space-y-2">
        {items.map((notification) => (
          <li
            key={notification.id}
            data-testid={`notification-${notification.id}`}
            className={`flex items-start justify-between gap-3 rounded-lg border p-4 ${
              notification.is_read
                ? 'bg-surface-container border-surface-container-highest opacity-70'
                : 'bg-surface-container border-primary/20'
            }`}
          >
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span
                  className={`text-[9px] font-mono font-bold uppercase px-1.5 py-0.5 rounded border ${SEVERITY_STYLES[notification.severity]}`}
                >
                  {notification.severity}
                </span>
                <span className="text-[10px] font-mono uppercase text-text-muted">
                  {notification.category}
                </span>
              </div>
              <p className="text-sm font-bold text-text-primary">{notification.title}</p>
              {notification.body && (
                <p className="text-xs text-text-secondary">{notification.body}</p>
              )}
              <p className="text-[10px] font-mono text-text-muted">
                {new Date(notification.created_at).toLocaleString()}
              </p>
            </div>
            {!notification.is_read && (
              <button
                onClick={() => markRead(notification, true)}
                className="flex items-center gap-1.5 px-2.5 py-1.5 rounded text-[10px] font-bold bg-primary/10 border border-primary/30 text-primary shrink-0"
              >
                <CheckCheck className="h-3.5 w-3.5" />
                Mark read
              </button>
            )}
          </li>
        ))}
      </ul>
    </div>
  );
};

export default NotificationsView;
