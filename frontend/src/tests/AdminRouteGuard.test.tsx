import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * `AdminRoute` (frontend/src/routes/AppRoutes.tsx) is the only gate standing
 * between a plain user and the admin UI - this proves it actually redirects
 * a non-admin to /access-denied and actually renders admin content for a
 * real admin, using the same real `AppRoutes` tree Playwright/production use
 * (not a hand-rolled stand-in for the guard).
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

let mockUser: { id: string; role: string; username: string; email: string } | null = null;
vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({
    user: mockUser,
    isLoading: false,
    logout: vi.fn(),
    login: vi.fn(),
    register: vi.fn(),
    enterLocalMode: vi.fn(),
    loginLocal: vi.fn(),
    setupAdmin: vi.fn(),
    // Redirected-to-/login renders the real LoginView, which checks this on
    // mount - resolving `false` (no setup needed) so the guard test exercises
    // the normal sign-in form, not the first-run admin-setup sub-state.
    checkAdminSetupNeeded: vi.fn().mockResolvedValue(false),
    errorMsg: null,
    infoMsg: null,
    clearError: vi.fn(),
    triggerSessionExpired: vi.fn(),
    isSessionExpired: false,
  }),
}));

import { AppRoutes } from '../routes/AppRoutes';

function renderAt(path: string) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <AppRoutes />
    </MemoryRouter>,
  );
}

describe('AdminRoute guard', () => {
  beforeEach(() => {
    authFetchMock.mockReset();
    authFetchMock.mockResolvedValue(new Response('{}', { status: 200 }));
  });

  it('redirects a plain user away from /admin/users to access-denied', async () => {
    mockUser = { id: 'u1', role: 'user', username: 'u1', email: 'u1@local' };
    renderAt('/admin/users');

    await waitFor(() => {
      expect(screen.getByText('Quyền Truy cập Bị hạn chế')).toBeTruthy();
    });
  });

  it('redirects an unauthenticated caller to /login', async () => {
    mockUser = null;
    renderAt('/admin/users');

    await waitFor(() => {
      expect(screen.getByText('Truy cập Security Console')).toBeTruthy();
    });
  });

  it('renders the real admin User Management view for an admin', async () => {
    mockUser = { id: 'admin-1', role: 'admin', username: 'root', email: 'root@local.admin.invalid' };
    authFetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          items: [
            {
              user_id: 'admin-1',
              email: 'root@local.admin.invalid',
              username: 'root',
              role: 'admin',
              is_active: true,
              source: 'local',
              is_test_account: false,
              created_at: '2026-08-05T00:00:00Z',
              updated_at: '2026-08-05T00:00:00Z',
              last_login_at: null,
            },
          ],
          total: 1,
          page: 1,
          page_size: 50,
        }),
        { status: 200 },
      ),
    );
    renderAt('/admin/users');

    await waitFor(() => {
      expect(screen.getByText('DB-backed administration for identities, roles, account state, and audit history.')).toBeTruthy();
    });
    expect(screen.getAllByText('root').length).toBeGreaterThan(0);
  });
});
