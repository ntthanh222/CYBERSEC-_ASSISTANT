import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Full Functional Audit found `AuthContext.toAppUser` hardcoded `role: 'user'`
 * for every session, which is exactly why /admin/* was permanently
 * unreachable (see DEAD_CODE_AND_GAPS_REPORT.md item 5). This test proves
 * the fix: the app role now comes from GET /api/auth/me (network-boundary
 * mocked here), not a hardcoded literal - it fails if AuthContext reverts.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

import { AuthProvider, useAuth } from '../features/auth/AuthContext';

function meResponse(role: 'user' | 'admin') {
  return new Response(
    JSON.stringify({ id: 'demo-user-id', email: 'local-demo@localhost', role, is_active: true }),
    { status: 200 },
  );
}

function localSessionResponse() {
  return new Response(
    JSON.stringify({
      access_token: 'fake-token',
      expires_at: Math.floor(Date.now() / 1000) + 3600,
      user: { id: 'demo-user-id', email: 'local-demo@localhost', created_at: '2026-08-05T00:00:00Z' },
    }),
    { status: 200 },
  );
}

function Probe() {
  const { user, enterLocalMode } = useAuth();
  return (
    <div>
      <button onClick={() => enterLocalMode()}>enter</button>
      <div data-testid="role">{user?.role ?? 'none'}</div>
    </div>
  );
}

describe('AuthContext app role is fetched from the backend', () => {
  const globalFetchMock = vi.fn();

  beforeEach(() => {
    authFetchMock.mockReset();
    globalFetchMock.mockReset();
    // authService.enterLocalMode() calls the plain global fetch (not the
    // authFetch wrapper - there is no session to attach a token from yet).
    vi.stubGlobal('fetch', globalFetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('reflects an admin role from GET /api/auth/me, not a hardcoded default', async () => {
    globalFetchMock.mockResolvedValue(localSessionResponse());
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/api/auth/me')) return Promise.resolve(meResponse('admin'));
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(
      <MemoryRouter>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MemoryRouter>,
    );

    await act(async () => {
      screen.getByText('enter').click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('role').textContent).toBe('admin');
    });
  });

  it('falls back to user (never admin) when the role lookup fails', async () => {
    globalFetchMock.mockResolvedValue(localSessionResponse());
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/api/auth/me')) return Promise.resolve(new Response('{}', { status: 500 }));
      throw new Error(`unexpected fetch: ${url}`);
    });

    render(
      <MemoryRouter>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MemoryRouter>,
    );

    await act(async () => {
      screen.getByText('enter').click();
    });

    await waitFor(() => {
      expect(screen.getByTestId('role').textContent).toBe('user');
    });
  });
});
