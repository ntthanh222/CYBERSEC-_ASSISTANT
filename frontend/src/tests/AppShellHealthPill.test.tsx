import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Codex round-1 finding: SystemHealthApi.test.tsx only tested the bare
 * getSystemHealth() client function, so it would still pass even if
 * AppShell.tsx were reverted to the old FixtureDataProvider mock. This test
 * renders the real AppShell and asserts the header pill reflects whatever
 * the (mocked-at-the-network-boundary) GET /api/system/health response
 * says - it fails if AppShell stops calling the real endpoint.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

// getSystemHealth() intentionally calls the unauthenticated global fetch
// (see frontend/src/lib/api/system.ts) - Phase 3.4 fixed it off of authFetch
// because it must work with no session at all (the connection-recovery
// layer needs it before login). Mock global fetch, not authFetch, here.
const globalFetchMock = vi.fn();

vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { email: 'test@localhost', username: 'test@localhost', id: 'test-user', role: 'user' },
    logout: vi.fn(),
  }),
}));

import { AppShell } from '../layouts/AppShell';

function healthResponse(status: 'healthy' | 'degraded') {
  const checkStatus = status === 'healthy' ? 'healthy' : 'unavailable';
  return new Response(
    JSON.stringify({
      status,
      timestamp: '2026-08-01T00:00:00+00:00',
      request_id: 'req-1',
      checks: {
        backend: { status: 'healthy', latency_ms: 0 },
        database: { status: 'healthy', latency_ms: 5 },
        redis: { status: checkStatus, latency_ms: 1 },
        migration: { status: 'healthy', latency_ms: 2 },
        pgvector: { status: 'healthy', latency_ms: 1 },
        local_auth_secret: { status: 'healthy', latency_ms: 1 },
      },
      embedding: { status: 'ready', elapsed_seconds: 10, error: null },
    }),
    { status: 200 },
  );
}

describe('AppShell header health pill', () => {
  beforeEach(() => {
    authFetchMock.mockReset();
    globalFetchMock.mockReset();
    vi.stubGlobal('fetch', globalFetchMock);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
  });

  it('renders SYS HEALTHY when GET /api/system/health reports healthy', async () => {
    globalFetchMock.mockResolvedValue(healthResponse('healthy'));

    render(
      <MemoryRouter>
        <AppShell>
          <div>content</div>
        </AppShell>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('HỆ THỐNG ỔN ĐỊNH')).toBeTruthy();
    });

    const [url] = globalFetchMock.mock.calls[0];
    expect(String(url)).toBe('/api/system/health');
  });

  it('renders SYS DEGRADED when GET /api/system/health reports a degraded dependency', async () => {
    globalFetchMock.mockResolvedValue(healthResponse('degraded'));

    render(
      <MemoryRouter>
        <AppShell>
          <div>content</div>
        </AppShell>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('HỆ THỐNG SUY GIẢM')).toBeTruthy();
    });
  });
});
