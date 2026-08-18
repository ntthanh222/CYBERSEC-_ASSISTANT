import { afterEach, describe, it, expect, vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Phase 3.3: GET /api/system/ai-health previously had no frontend caller.
 * This test renders the real AdminOverviewView and asserts the AI Assistant
 * Provider card reflects the real ai-health response, not a fixture - it
 * fails if the card reverts to hardcoded text or is removed.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

import { AdminOverviewView } from '../features/admin/views/AdminOverviewView';

function summaryResponse() {
  return new Response(
    JSON.stringify({
      users: {
        total: 1,
        admins: 1,
        active: 1,
        disabled: 0,
        users: 0,
        security_analysts: 0,
        super_admins: 1,
        demo: 0,
        test: 0,
        local: 1,
        hosted: 0,
      },
      content: { documents: 0, conversations: 0, messages: 0, scans: 0 },
      system_status: 'healthy',
      audit_events: 0,
      recent_admin_actions: 0,
    }),
    { status: 200 },
  );
}

function systemHealthResponse() {
  return new Response(
    JSON.stringify({
      status: 'healthy',
      timestamp: '2026-08-08T00:00:00Z',
      request_id: 'test',
      checks: {
        backend: { status: 'healthy', latency_ms: 0 },
        database: { status: 'healthy', latency_ms: 1 },
        redis: { status: 'healthy', latency_ms: 1 },
        migration: { status: 'healthy', latency_ms: 1 },
        pgvector: { status: 'healthy', latency_ms: 1 },
        local_auth_secret: { status: 'healthy', latency_ms: 1 },
      },
      embedding: { status: 'ready', elapsed_seconds: 1, error: null },
    }),
    { status: 200 },
  );
}

function aiHealthResponse(overrides: Record<string, unknown> = {}) {
  return new Response(
    JSON.stringify({
      status: 'degraded',
      provider: 'local',
      provider_configured: false,
      fallback_provider: 'local',
      rag_ready: true,
      rag_documents: 0,
      detail: 'No external AI provider is configured (GEMINI_API_KEY is unset).',
      ...overrides,
    }),
    { status: 200 },
  );
}

describe('Admin Overview AI health panel', () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('renders the real AI provider status from the ai-health endpoint', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(systemHealthResponse()));
    authFetchMock.mockImplementation((url: string) => {
      if (url.includes('/api/system/ai-health')) return Promise.resolve(aiHealthResponse());
      return Promise.resolve(summaryResponse());
    });

    render(
      <MemoryRouter initialEntries={['/admin/rag']}>
        <AdminOverviewView />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText(/GEMINI_API_KEY is unset/)).toBeTruthy(),
    );
    expect(screen.getByText(/RAG ready/i)).toBeTruthy();
    expect(
      authFetchMock.mock.calls.some(([url]) => String(url).includes('/api/system/ai-health')),
    ).toBe(true);
  });

  it('shows a configured-provider state distinctly from the local-fallback state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(systemHealthResponse()));
    authFetchMock.mockImplementation((url: string) => {
      if (url.includes('/api/system/ai-health')) {
        return Promise.resolve(
          aiHealthResponse({
            status: 'healthy',
            provider: 'gemini',
            provider_configured: true,
            detail: 'External AI provider configured; deep mode uses it.',
          }),
        );
      }
      return Promise.resolve(summaryResponse());
    });

    render(
      <MemoryRouter initialEntries={['/admin/rag']}>
        <AdminOverviewView />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByText(/deep mode uses it/i)).toBeTruthy());
    expect(screen.queryByText(/local fallback/i)).not.toBeTruthy();
  });
});
