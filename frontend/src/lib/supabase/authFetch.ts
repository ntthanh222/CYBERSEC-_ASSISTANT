import { getAccessToken, signOut } from './authService';

export class UnauthenticatedError extends Error {
  constructor() {
    super('No active Supabase session.');
    this.name = 'UnauthenticatedError';
  }
}

/**
 * `fetch` wrapper that attaches `Authorization: Bearer <supabase-access-token>`
 * to every call - the only place a request to a private backend route should
 * be made from. Never accepts a caller-supplied user id; the backend derives
 * identity solely from this token's `sub` claim.
 *
 * On a 401 response (token rejected by the backend - expired, wrong
 * project, refresh genuinely failed) this signs the user out so the app
 * returns to a clean logged-out state rather than silently retrying with a
 * token the backend has already rejected.
 */
export async function authFetch(input: string, init: RequestInit = {}): Promise<Response> {
  const token = await getAccessToken();
  if (!token) {
    await signOut();
    throw new UnauthenticatedError();
  }

  const headers = new Headers(init.headers);
  headers.set('Authorization', `Bearer ${token}`);

  const response = await fetch(input, { ...init, headers });
  if (response.status === 401) {
    await signOut();
    throw new UnauthenticatedError();
  }
  return response;
}
