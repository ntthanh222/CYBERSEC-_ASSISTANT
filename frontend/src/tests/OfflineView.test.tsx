import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Phase 3.4: the old OfflineView was entirely fake ("For demonstration, we
 * keep it offline" - Retry never actually checked anything). This proves
 * the real view renders live connection state from the shared provider and
 * that Retry calls the real checkNow function, not a fake timeout.
 */
const mockState = {
  status: 'backend_unreachable' as const,
  checks: {
    backend: { status: 'unavailable', latency_ms: null },
    database: { status: 'healthy', latency_ms: 5 },
    redis: { status: 'healthy', latency_ms: 1 },
    migration: { status: 'healthy', latency_ms: 2 },
    pgvector: { status: 'healthy', latency_ms: 1 },
    local_auth_secret: { status: 'healthy', latency_ms: 1 },
  },
  embedding: { status: 'ready' as const, elapsed_seconds: 3, error: null },
  lastCheckedAt: Date.now(),
  checkNow: vi.fn(),
};

vi.mock('../lib/network/ConnectionRecoveryProvider', () => ({
  useBackendAvailability: () => mockState,
}));

import { OfflineView } from '../features/auth/login/OfflineView';

describe('OfflineView', () => {
  it('renders the real backend-unreachable state, not a fixed fake message', () => {
    render(
      <MemoryRouter>
        <OfflineView />
      </MemoryRouter>,
    );
    expect(screen.getByText('Không thể kết nối máy chủ backend')).toBeTruthy();
    expect(screen.getByText(/unavailable/i)).toBeTruthy();
    expect(screen.getAllByText(/backend/i).length).toBeGreaterThan(0);
  });

  it('calls the real checkNow function on Retry, not a fake setTimeout', () => {
    mockState.checkNow.mockClear();
    render(
      <MemoryRouter>
        <OfflineView />
      </MemoryRouter>,
    );
    fireEvent.click(screen.getByText(/THỬ LẠI KẾT NỐI/i));
    expect(mockState.checkNow).toHaveBeenCalledTimes(1);
  });

  it('never renders a stack trace, DSN, or secret-shaped string', () => {
    render(
      <MemoryRouter>
        <OfflineView />
      </MemoryRouter>,
    );
    const text = document.body.textContent ?? '';
    expect(text).not.toMatch(/postgresql:\/\//i);
    expect(text).not.toMatch(/Traceback/i);
    expect(text).not.toMatch(/at\s+\S+\.(js|ts|tsx):\d+/);
  });
});
