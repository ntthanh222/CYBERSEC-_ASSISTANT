import { apiGet } from './client';

export type AppRole = 'user' | 'security_analyst' | 'admin' | 'super_admin';

export interface MeResponse {
  id: string;
  email: string | null;
  role: AppRole;
  is_active: boolean;
}

/** The caller's DB-backed app role - never trust a client-side default. */
export function getMe(): Promise<MeResponse> {
  return apiGet<MeResponse>('/api/auth/me');
}
