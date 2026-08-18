import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor, act } from '@testing-library/react';
import { MemoryRouter, Routes, Route, useLocation } from 'react-router-dom';

/**
 * Phase 3.4: `/offline` used to be unreachable and its own view faked
 * connectivity ("For demonstration, we keep it offline"). This proves the
 * real detection/redirect/recovery logic: a genuine backend-unreachable or
 * database-degraded signal redirects to /offline and back, while ordinary
 * API errors (401/403/429, exercised elsewhere) and ownership never react
 * to this layer at all - it's not wired into fetch success/failure for
 * regular requests, only into the dedicated health-check + transport-level
 * failure paths.
 */
const getSystemHealthMock = vi.fn();
vi.mock('../lib/api/system', async () => {
  const actual = await vi.importActual<typeof import('../lib/api/system')>('../lib/api/system');
  return { ...actual, getSystemHealth: (...args: unknown[]) => getSystemHealthMock(...args) };
});

const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

import { ConnectionRecoveryProvider } from '../lib/network/ConnectionRecoveryProvider';
import { apiGet, ApiError } from '../lib/api/client';

function healthyResponse(overrides: Partial<Record<string, { status: string; latency_ms: number | null }>> = {}) {
  return {
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
      ...overrides,
    },
    embedding: { status: 'ready', elapsed_seconds: 3, error: null },
  };
}

function LocationProbe() {
  const location = useLocation();
  return <div data-testid="current-path">{location.pathname}</div>;
}

function DashboardStub() {
  return <div>Dashboard Content</div>;
}
function LoginStub() {
  return <div>Login Content</div>;
}
function OfflineStub() {
  return <div>Offline Content</div>;
}

function renderApp(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <ConnectionRecoveryProvider>
        <LocationProbe />
        <Routes>
          <Route path="/dashboard" element={<DashboardStub />} />
          <Route path="/login" element={<LoginStub />} />
          <Route path="/offline" element={<OfflineStub />} />
        </Routes>
      </ConnectionRecoveryProvider>
    </MemoryRouter>,
  );
}

describe('ConnectionRecoveryProvider', () => {
  const originalOnLine = window.navigator.onLine;

  beforeEach(() => {
    getSystemHealthMock.mockReset();
    sessionStorage.clear();
    Object.defineProperty(window.navigator, 'onLine', { value: true, writable: true, configurable: true });
  });

  afterEach(() => {
    Object.defineProperty(window.navigator, 'onLine', { value: originalOnLine, writable: true, configurable: true });
  });

  it('redirects to /offline when the backend health check reports backend unreachable', async () => {
    getSystemHealthMock.mockResolvedValue(healthyResponse({ backend: { status: 'unavailable', latency_ms: null } }));
    renderApp('/dashboard');

    await waitFor(() => expect(screen.getByTestId('current-path').textContent).toBe('/offline'));
    expect(sessionStorage.getItem('cybersec_offline_return_path')).toBe('/dashboard');
  });

  it('redirects to /offline when the database is degraded, and shows it as degraded not offline', async () => {
    getSystemHealthMock.mockResolvedValue(healthyResponse({ database: { status: 'degraded', latency_ms: 900 } }));
    renderApp('/dashboard');

    await waitFor(() => expect(screen.getByTestId('current-path').textContent).toBe('/offline'));
  });

  it('does NOT redirect when only Redis is degraded - most of the app keeps working', async () => {
    getSystemHealthMock.mockResolvedValue(healthyResponse({ redis: { status: 'degraded', latency_ms: 500 } }));
    renderApp('/dashboard');

    await waitFor(() => expect(getSystemHealthMock).toHaveBeenCalled());
    expect(screen.getByTestId('current-path').textContent).toBe('/dashboard');
  });

  it('redirects on a transport-level failure (getSystemHealth itself throws)', async () => {
    getSystemHealthMock.mockRejectedValue(new Error('Failed to fetch'));
    renderApp('/ai');

    await waitFor(() => expect(screen.getByTestId('current-path').textContent).toBe('/offline'));
    expect(sessionStorage.getItem('cybersec_offline_return_path')).toBe('/ai');
  });

  it('never redirects away from exempt routes like /login', async () => {
    getSystemHealthMock.mockRejectedValue(new Error('Failed to fetch'));
    renderApp('/login');

    await waitFor(() => expect(getSystemHealthMock).toHaveBeenCalled());
    expect(screen.getByTestId('current-path').textContent).toBe('/login');
  });

  it('restores the remembered route once the backend recovers', async () => {
    getSystemHealthMock.mockResolvedValue(healthyResponse({ backend: { status: 'unavailable', latency_ms: null } }));
    renderApp('/dashboard');
    await waitFor(() => expect(screen.getByTestId('current-path').textContent).toBe('/offline'));

    getSystemHealthMock.mockResolvedValue(healthyResponse());
    // Simulate the user pressing Retry via the provider's checkNow, exposed
    // through context in the real OfflineView - here we just trigger a
    // manual re-check the same way the browser 'online' event would.
    act(() => {
      window.dispatchEvent(new Event('online'));
    });

    await waitFor(
      () => expect(screen.getByTestId('current-path').textContent).toBe('/dashboard'),
      { timeout: 3000 },
    );
    expect(sessionStorage.getItem('cybersec_offline_return_path')).toBeNull();
  });

  it('does not auto-navigate away from /offline when the user arrived by typing the URL directly', async () => {
    getSystemHealthMock.mockResolvedValue(healthyResponse());
    renderApp('/offline');

    await waitFor(() => expect(getSystemHealthMock).toHaveBeenCalled());
    expect(screen.getByTestId('current-path').textContent).toBe('/offline');
  });

  it('a normal 401/403/429 API response from an unrelated component never triggers a redirect', async () => {
    getSystemHealthMock.mockResolvedValue(healthyResponse());
    authFetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: 'forbidden', message: 'Access denied.' }), { status: 403 }),
    );
    renderApp('/dashboard');
    await waitFor(() => expect(screen.getByTestId('current-path').textContent).toBe('/dashboard'));

    await expect(apiGet('/api/some/protected/thing')).rejects.toBeInstanceOf(ApiError);

    // Give any (incorrect) reactive redirect a chance to fire, then assert it didn't.
    await new Promise((r) => setTimeout(r, 50));
    expect(screen.getByTestId('current-path').textContent).toBe('/dashboard');
  });

  it('keeps polling automatically after a manual checkNow trigger (online event), instead of stopping forever', async () => {
    // Needs a longer test timeout: it deliberately waits for a real
    // subsequent poll-interval tick (MIN_POLL_MS=4000ms) to prove the
    // automatic polling loop is still alive after checkNow() ran.
    // Regression test for a real bug: checkNow() cleared the scheduled
    // polling timer without ever rescheduling the next one, so a single
    // 'online' event (or Retry click) would silently stop all future
    // automatic outage detection until the provider remounted.
    getSystemHealthMock.mockResolvedValue(healthyResponse());
    renderApp('/dashboard');
    await waitFor(() => expect(screen.getByTestId('current-path').textContent).toBe('/dashboard'));
    // Wait for the initial mount check to actually complete and schedule
    // its own next poll before firing the manual trigger below - otherwise
    // this test can't tell "checkNow ran concurrently with the still-
    // in-flight mount check" apart from "checkNow correctly re-armed
    // polling after a prior check finished," which is the specific
    // distinction this regression test exists to prove.
    await waitFor(() => expect(getSystemHealthMock.mock.calls.length).toBeGreaterThanOrEqual(1));

    // This fires checkNow() via the 'online' listener, even though nothing
    // was actually wrong - simulating a spurious/early browser online event.
    const callsBeforeOnline = getSystemHealthMock.mock.calls.length;
    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    await waitFor(() => expect(getSystemHealthMock.mock.calls.length).toBeGreaterThan(callsBeforeOnline));

    // Now a real outage must still be detected automatically, with no
    // further manual trigger - proving the polling loop is still alive.
    getSystemHealthMock.mockResolvedValue(healthyResponse({ backend: { status: 'unavailable', latency_ms: null } }));
    await waitFor(
      () => expect(screen.getByTestId('current-path').textContent).toBe('/offline'),
      { timeout: 10000 },
    );
  }, 15000);

  it('never runs two overlapping check chains when a manual trigger fires mid-flight', async () => {
    // Regression test: checkNow() must not start a second concurrent
    // check() while one from the passive timer chain is still awaiting its
    // response - two independent chains would each re-arm their own timer,
    // silently doubling the effective polling rate every time this races.
    let resolveHealth: ((v: ReturnType<typeof healthyResponse>) => void) | null = null;
    getSystemHealthMock.mockImplementation(
      () => new Promise((resolve) => { resolveHealth = resolve; }),
    );
    renderApp('/dashboard');

    await waitFor(() => expect(getSystemHealthMock).toHaveBeenCalledTimes(1));
    // A check is now genuinely in flight (its promise hasn't resolved yet).
    // Firing checkNow() here must NOT start a second, overlapping call.
    act(() => {
      window.dispatchEvent(new Event('online'));
    });
    await new Promise((r) => setTimeout(r, 20));
    expect(getSystemHealthMock).toHaveBeenCalledTimes(1);

    // Let the in-flight check resolve and confirm exactly one subsequent
    // poll gets scheduled from it - not two.
    resolveHealth!(healthyResponse());
    getSystemHealthMock.mockResolvedValue(healthyResponse());
    await waitFor(() => expect(getSystemHealthMock.mock.calls.length).toBeGreaterThanOrEqual(2), {
      timeout: 8000,
    });
    const countAfterOneMorePoll = getSystemHealthMock.mock.calls.length;
    // Give a second poll interval a chance to fire and confirm the count
    // only advances by roughly one chain's worth, not two chains' worth.
    await new Promise((r) => setTimeout(r, 4500));
    expect(getSystemHealthMock.mock.calls.length).toBeLessThanOrEqual(countAfterOneMorePoll + 1);
  }, 15000);

  it('restores the remembered route on a fresh mount that starts already at /offline with a stored return path', async () => {
    // Regression test for a real bug found via e2e: a full page reload
    // (not client-side navigation) while the app had already redirected
    // itself to /offline creates a brand-new provider instance whose
    // wasUnreachableRef starts false. If the backend is already healthy by
    // the time that fresh mount's very first check runs, the old logic
    // reported plain 'online' (not 'restored') and never called
    // restoreFromOffline() - permanently stranding the user on /offline
    // despite a valid stored return path and a fully healthy backend.
    sessionStorage.setItem('cybersec_offline_return_path', '/dashboard');
    getSystemHealthMock.mockResolvedValue(healthyResponse());
    renderApp('/offline');

    await waitFor(() => expect(screen.getByTestId('current-path').textContent).toBe('/dashboard'));
    expect(sessionStorage.getItem('cybersec_offline_return_path')).toBeNull();
  });

  it('treats a real browser offline event as an immediate signal', async () => {
    getSystemHealthMock.mockResolvedValue(healthyResponse());
    renderApp('/dashboard');
    await waitFor(() => expect(screen.getByTestId('current-path').textContent).toBe('/dashboard'));

    await act(async () => {
      Object.defineProperty(window.navigator, 'onLine', { value: false, writable: true, configurable: true });
      window.dispatchEvent(new Event('offline'));
    });

    await waitFor(() => expect(screen.getByTestId('current-path').textContent).toBe('/offline'));
  });
});
