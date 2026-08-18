import { describe, it, expect, vi, beforeEach } from 'vitest';

/**
 * Phase 3.4: the API client must distinguish a real HTTP error response
 * (ApiError - proof the backend IS reachable) from a transport-level
 * failure (NetworkUnavailableError - the request never got a response at
 * all), and must never misclassify a missing/rejected session
 * (UnauthenticatedError, handled by the existing auth flow) as a network
 * outage.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
  UnauthenticatedError: class UnauthenticatedError extends Error {
    constructor() {
      super('No active session.');
      this.name = 'UnauthenticatedError';
    }
  },
}));

import { apiGet, ApiError, NetworkUnavailableError, onNetworkFailure } from '../lib/api/client';

describe('API client transport-failure handling', () => {
  beforeEach(() => {
    authFetchMock.mockReset();
  });

  it('throws NetworkUnavailableError when fetch itself fails, and notifies listeners', async () => {
    authFetchMock.mockRejectedValue(new TypeError('Failed to fetch'));
    const listener = vi.fn();
    const unsubscribe = onNetworkFailure(listener);

    await expect(apiGet('/api/system/health')).rejects.toBeInstanceOf(NetworkUnavailableError);
    expect(listener).toHaveBeenCalledTimes(1);
    unsubscribe();
  });

  it('throws ApiError (not NetworkUnavailableError) for a real 404 response', async () => {
    authFetchMock.mockResolvedValue(
      new Response(JSON.stringify({ error: 'not_found', message: 'Not found.' }), { status: 404 }),
    );

    await expect(apiGet('/api/knowledge/documents/x')).rejects.toBeInstanceOf(ApiError);
  });

  it('does not treat a missing/rejected session as a network outage', async () => {
    const { UnauthenticatedError } = await import('../lib/supabase/authFetch');
    authFetchMock.mockRejectedValue(new UnauthenticatedError());
    const listener = vi.fn();
    const unsubscribe = onNetworkFailure(listener);

    await expect(apiGet('/api/auth/me')).rejects.toMatchObject({ name: 'UnauthenticatedError' });
    
    expect(listener).not.toHaveBeenCalled();
    unsubscribe();
  });
});
