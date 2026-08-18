import { apiGet, apiPatch } from './client';
import type { Page } from './chatbot';

export type NotificationCategory = 'alert' | 'incident' | 'vulnerability' | 'system';
export type NotificationSeverity = 'info' | 'warning' | 'critical';

export interface NotificationRecord {
  id: string;
  title: string;
  body: string;
  category: NotificationCategory;
  severity: NotificationSeverity;
  is_read: boolean;
  source_ref: string;
  created_at: string;
  updated_at: string;
}

export interface NotificationPage extends Page<NotificationRecord> {
  unread_count: number;
}

export function listNotifications(unreadOnly = false): Promise<NotificationPage> {
  const params = new URLSearchParams();
  params.set('page', '1');
  params.set('page_size', '100');
  if (unreadOnly) params.set('unread_only', 'true');
  return apiGet<NotificationPage>(`/api/notifications?${params.toString()}`);
}

export function setNotificationRead(id: string, isRead: boolean): Promise<NotificationRecord> {
  return apiPatch<NotificationRecord>(`/api/notifications/${id}/read`, { is_read: isRead });
}
