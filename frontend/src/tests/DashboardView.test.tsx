import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Full Functional Audit found the header health pill wired to fixture data
 * (see AppShellHealthPill.test.tsx). The Dashboard had the same defect one
 * layer deeper: every card read from FixtureDataProvider's static mocks
 * (hardcoded "Zerologon" AI briefing text, a fixed 7-point chart array, a
 * literal "5" for the CVE count) instead of the real per-user counts the
 * backend already exposed at GET /api/system/dashboard-summary. This test
 * renders the real DashboardView and asserts every number comes from the
 * (network-boundary-mocked) API response, not from a fixture import - it
 * fails if DashboardView reverts to FixtureDataProvider.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

// getSystemHealth() calls unauthenticated global fetch, not authFetch (see
// frontend/src/lib/api/system.ts, fixed in Phase 3.4) - route it separately.
const globalFetchMock = vi.fn();

import { DashboardView } from '../features/dashboard/DashboardView';

function summaryResponse(overrides: Partial<{ documents: number; conversations: number; messages: number; scans: number }> = {}) {
  const counts = { documents: 2, conversations: 3, messages: 11, scans: 4, ...overrides };
  return new Response(
    JSON.stringify({
      counts,
      recent_activity: [
        {
          type: 'document',
          id: 'doc-1',
          title: 'phase3-final-marker-doc.txt',
          detail: 'ready',
          created_at: '2026-08-05T10:00:00+00:00',
          href: '/knowledge-base',
        },
      ],
    }),
    { status: 200 },
  );
}

function healthResponse() {
  return new Response(
    JSON.stringify({
      status: 'healthy',
      timestamp: '2026-08-05T10:00:00+00:00',
      request_id: 'req-1',
      checks: {
        backend: { status: 'healthy', latency_ms: 0 },
        database: { status: 'healthy', latency_ms: 5 },
        redis: { status: 'healthy', latency_ms: 1 },
        migration: { status: 'healthy', latency_ms: 2 },
        pgvector: { status: 'healthy', latency_ms: 1 },
        local_auth_secret: { status: 'healthy', latency_ms: 1 },
      },
      embedding: { status: 'ready', elapsed_seconds: 3, error: null },
    }),
    { status: 200 },
  );
}

function routeFetch(summary: Response, health: Response = healthResponse()) {
  authFetchMock.mockImplementation((url: string) => {
    if (String(url).includes('dashboard-summary')) return Promise.resolve(summary.clone());
    throw new Error(`unexpected authFetch: ${url}`);
  });
  globalFetchMock.mockImplementation((url: string) => {
    if (String(url).includes('/api/system/health')) return Promise.resolve(health.clone());
    throw new Error(`unexpected fetch: ${url}`);
  });
}

describe('DashboardView', () => {
  beforeEach(() => {
    authFetchMock.mockReset();
    globalFetchMock.mockReset();
    vi.stubGlobal('fetch', globalFetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders real counts from the API, not fixture numbers', async () => {
    routeFetch(summaryResponse({ documents: 2, conversations: 3, messages: 11, scans: 4 }));

    render(
      <MemoryRouter>
        <DashboardView />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('2')).toBeTruthy();
      expect(screen.getByText('3')).toBeTruthy();
      expect(screen.getByText('4')).toBeTruthy();
    });
    expect(screen.getByText('11 tin nhắn')).toBeTruthy();

    // The old fixture-only content must be gone.
    expect(screen.queryByText(/Zerologon/i)).toBeNull();
  });

  it('shows an honest empty state when the account has no data, never a random number', async () => {
    routeFetch(summaryResponse({ documents: 0, conversations: 0, messages: 0, scans: 0 }));
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('dashboard-summary')) {
        return Promise.resolve(
          new Response(JSON.stringify({ counts: { documents: 0, conversations: 0, messages: 0, scans: 0 }, recent_activity: [] }), {
            status: 200,
          }),
        );
      }
      throw new Error(`unexpected authFetch: ${url}`);
    });

    render(
      <MemoryRouter>
        <DashboardView />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText('Chưa có hoạt động nào.')).toBeTruthy();
    });
  });

  it('shows a retry control when the summary request fails, not a blank or fake screen', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('dashboard-summary')) {
        return Promise.resolve(new Response(JSON.stringify({ error: 'internal', message: 'boom', request_id: 'r1' }), { status: 500 }));
      }
      throw new Error(`unexpected authFetch: ${url}`);
    });
    globalFetchMock.mockResolvedValue(healthResponse());

    render(
      <MemoryRouter>
        <DashboardView />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/Thử lại/i)).toBeTruthy();
    });
  });
});
