import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

// Functional-audit regression: the header health pill used to be wired to
// FixtureDataProvider (a mock) and could show "SYS DEGRADED" while the real
// stack was fully healthy. It must now call the real readiness endpoint.
//
// Phase 3.4: getSystemHealth() calls unauthenticated global fetch, not
// authFetch - /api/system/health is a public readiness endpoint that must
// work with no session at all (the connection-recovery layer needs it
// before login). See frontend/src/lib/api/system.ts.
const globalFetchMock = vi.fn();

import { getSystemHealth } from '../lib/api/system';

describe('getSystemHealth', () => {
  beforeEach(() => {
    globalFetchMock.mockReset();
    vi.stubGlobal('fetch', globalFetchMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('calls the real GET /api/system/health endpoint (unauthenticated) and returns real check data', async () => {
    globalFetchMock.mockResolvedValue(
      new Response(
        JSON.stringify({
          status: 'healthy',
          timestamp: '2026-08-01T00:00:00+00:00',
          request_id: 'req-1',
          checks: {
            backend: { status: 'healthy', latency_ms: 0 },
            database: { status: 'healthy', latency_ms: 5 },
            redis: { status: 'healthy', latency_ms: 1 },
            migration: { status: 'healthy', latency_ms: 2 },
            pgvector: { status: 'healthy', latency_ms: 1 },
            local_auth_secret: { status: 'healthy', latency_ms: 1 },
          },
          embedding: { status: 'ready', elapsed_seconds: 10, error: null },
        }),
        { status: 200 },
      ),
    );

    const result = await getSystemHealth();

    expect(globalFetchMock).toHaveBeenCalled();
    const [url] = globalFetchMock.mock.calls[0];
    expect(String(url)).toBe('/api/system/health');
    expect(result.status).toBe('healthy');
    expect(result.checks.database.status).toBe('healthy');
  });

  it('works with no Authorization header present at all (no session)', async () => {
    globalFetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      const headers = new Headers(init?.headers);
      expect(headers.has('Authorization')).toBe(false);
      return Promise.resolve(
        new Response(
          JSON.stringify({
            status: 'healthy',
            timestamp: '2026-08-01T00:00:00+00:00',
            request_id: 'req-1',
            checks: {
              backend: { status: 'healthy', latency_ms: 0 },
              database: { status: 'healthy', latency_ms: 5 },
              redis: { status: 'healthy', latency_ms: 1 },
              migration: { status: 'healthy', latency_ms: 2 },
              pgvector: { status: 'healthy', latency_ms: 1 },
              local_auth_secret: { status: 'healthy', latency_ms: 1 },
            },
            embedding: { status: 'ready', elapsed_seconds: 10, error: null },
          }),
          { status: 200 },
        ),
      );
    });

    await expect(getSystemHealth()).resolves.toMatchObject({ status: 'healthy' });
  });
});
