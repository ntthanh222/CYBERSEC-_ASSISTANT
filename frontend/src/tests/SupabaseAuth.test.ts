import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

const mockAuth = {
  signUp: vi.fn(),
  signInWithPassword: vi.fn(),
  signOut: vi.fn(),
  getSession: vi.fn(),
  onAuthStateChange: vi.fn(),
};

vi.mock('@supabase/supabase-js', () => ({
  createClient: vi.fn(() => ({ auth: mockAuth })),
}));

import { _resetSupabaseClientForTests, getSupabaseClient } from '../lib/supabase/client';
import {
  getAccessToken,
  getSession,
  onAuthStateChange,
  signIn,
  signOut,
  signUp,
} from '../lib/supabase/authService';
import { authFetch, UnauthenticatedError } from '../lib/supabase/authFetch';
import { enterLocalMode } from '../lib/supabase/authService';

function setEnv(url?: string, key?: string) {
  if (url === undefined) {
    vi.stubEnv('VITE_SUPABASE_URL', '');
  } else {
    vi.stubEnv('VITE_SUPABASE_URL', url);
  }
  if (key === undefined) {
    vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', '');
  } else {
    vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', key);
  }
}

describe('supabase client', () => {
  beforeEach(() => {
    _resetSupabaseClientForTests();
    setEnv('https://project-ref.supabase.co', 'publishable-key');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('throws a clear error when unconfigured', () => {
    setEnv(undefined, undefined);
    expect(() => getSupabaseClient()).toThrow(/not configured/);
  });

  it('creates a single client instance', () => {
    const first = getSupabaseClient();
    const second = getSupabaseClient();
    expect(first).toBe(second);
  });
});

describe('authService', () => {
  beforeEach(() => {
    _resetSupabaseClientForTests();
    setEnv('https://project-ref.supabase.co', 'publishable-key');
    vi.clearAllMocks();
  });

  it('signUp returns ok on success', async () => {
    mockAuth.signUp.mockResolvedValue({ error: null });
    const result = await signUp('a@example.com', 'test-password');
    expect(result.ok).toBe(true);
    expect(mockAuth.signUp).toHaveBeenCalledWith({
      email: 'a@example.com',
      password: 'test-password',
    });
  });

  it('signUp surfaces the error message on failure', async () => {
    mockAuth.signUp.mockResolvedValue({ error: { message: 'Email already registered' } });
    const result = await signUp('a@example.com', 'x');
    expect(result).toEqual({ ok: false, error: 'Email already registered' });
  });

  it('signIn returns ok on success', async () => {
    mockAuth.signInWithPassword.mockResolvedValue({ error: null });
    const result = await signIn('a@example.com', 'hunter2-very-long');
    expect(result.ok).toBe(true);
  });

  it('signIn surfaces the error message on failure', async () => {
    mockAuth.signInWithPassword.mockResolvedValue({ error: { message: 'Invalid credentials' } });
    const result = await signIn('a@example.com', 'wrong');
    expect(result).toEqual({ ok: false, error: 'Invalid credentials' });
  });

  it('signOut delegates to the client', async () => {
    mockAuth.signOut.mockResolvedValue({ error: null });
    await signOut();
    expect(mockAuth.signOut).toHaveBeenCalled();
  });

  it('getSession returns the current session', async () => {
    const fakeSession = { access_token: 'abc.def.ghi', user: { id: 'u1' } };
    mockAuth.getSession.mockResolvedValue({ data: { session: fakeSession } });
    const session = await getSession();
    expect(session).toBe(fakeSession);
  });

  it('getSession returns null when signed out', async () => {
    mockAuth.getSession.mockResolvedValue({ data: { session: null } });
    expect(await getSession()).toBeNull();
  });

  it('getAccessToken returns the token from the current session', async () => {
    mockAuth.getSession.mockResolvedValue({
      data: { session: { access_token: 'the-token', user: { id: 'u1' } } },
    });
    expect(await getAccessToken()).toBe('the-token');
  });

  it('getAccessToken returns null when there is no session', async () => {
    mockAuth.getSession.mockResolvedValue({ data: { session: null } });
    expect(await getAccessToken()).toBeNull();
  });

  it('onAuthStateChange forwards the user and returns an unsubscribe function', () => {
    const unsubscribe = vi.fn();
    mockAuth.onAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      cb('SIGNED_IN', { user: { id: 'u1' } });
      return { data: { subscription: { unsubscribe } } };
    });

    const handler = vi.fn();
    const stop = onAuthStateChange(handler);
    expect(handler).toHaveBeenCalledWith({ id: 'u1' });

    stop();
    expect(unsubscribe).toHaveBeenCalled();
  });

  it('onAuthStateChange reports null on sign-out / failed refresh', () => {
    mockAuth.onAuthStateChange.mockImplementation((cb: (event: string, session: unknown) => void) => {
      cb('SIGNED_OUT', null);
      return { data: { subscription: { unsubscribe: vi.fn() } } };
    });

    const handler = vi.fn();
    onAuthStateChange(handler);
    expect(handler).toHaveBeenCalledWith(null);
  });
});

describe('authFetch', () => {
  beforeEach(() => {
    _resetSupabaseClientForTests();
    setEnv('https://project-ref.supabase.co', 'publishable-key');
    vi.clearAllMocks();
    vi.stubGlobal('fetch', vi.fn());
  });

  it('throws UnauthenticatedError when there is no session', async () => {
    mockAuth.getSession.mockResolvedValue({ data: { session: null } });
    await expect(authFetch('/api/chatbot/conversations')).rejects.toBeInstanceOf(
      UnauthenticatedError,
    );
    expect(fetch).not.toHaveBeenCalled();
  });

  it('attaches the Authorization header from the current session', async () => {
    mockAuth.getSession.mockResolvedValue({
      data: { session: { access_token: 'real-token', user: { id: 'u1' } } },
    });
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('{}', { status: 200 }),
    );

    await authFetch('/api/chatbot/conversations');

    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer real-token');
  });

  it('never lets caller-supplied headers override the Authorization header', async () => {
    mockAuth.getSession.mockResolvedValue({
      data: { session: { access_token: 'real-token', user: { id: 'u1' } } },
    });
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('{}', { status: 200 }),
    );

    await authFetch('/api/chatbot/conversations', {
      headers: { Authorization: 'Bearer client-supplied-forgery' },
    });

    const [, init] = (fetch as unknown as ReturnType<typeof vi.fn>).mock.calls[0];
    const headers = new Headers(init.headers);
    expect(headers.get('Authorization')).toBe('Bearer real-token');
  });

  it('signs the user out on a 401 response and throws UnauthenticatedError', async () => {
    mockAuth.getSession.mockResolvedValue({
      data: { session: { access_token: 'stale-token', user: { id: 'u1' } } },
    });
    mockAuth.signOut.mockResolvedValue({ error: null });
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('{}', { status: 401 }),
    );

    await expect(authFetch('/api/chatbot/conversations')).rejects.toBeInstanceOf(UnauthenticatedError);

    expect(mockAuth.signOut).toHaveBeenCalled();
  });
});

describe('Local Mode session (Docker one-command, no hosted Supabase)', () => {
  beforeEach(() => {
    localStorage.clear();
    _resetSupabaseClientForTests();
    // No Supabase configuration at all - the default for the Docker-local
    // stack, which never has a frontend/.env.
    setEnv(undefined, undefined);
    vi.clearAllMocks();
    vi.stubGlobal('fetch', vi.fn());
  });

  it('enterLocalMode posts to the backend and persists the session', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: 'local.jwt.token',
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          user: { id: 'demo-user', email: 'local-demo@localhost', created_at: '2026-01-01T00:00:00Z' },
        }),
        { status: 200 },
      ),
    );

    const result = await enterLocalMode();

    expect(result.ok).toBe(true);
    expect(fetch).toHaveBeenCalledWith('/api/auth/local-session', { method: 'POST' });
    expect(await getAccessToken()).toBe('local.jwt.token');
  });

  it('enterLocalMode fails gracefully when the endpoint 404s (not APP_ENV=local)', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response('{}', { status: 404 }),
    );

    const result = await enterLocalMode();

    expect(result.ok).toBe(false);
    expect(await getAccessToken()).toBeNull();
  });

  it('getSession never touches the Supabase client for a local session', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: 'local.jwt.token',
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          user: { id: 'demo-user', email: 'local-demo@localhost', created_at: '2026-01-01T00:00:00Z' },
        }),
        { status: 200 },
      ),
    );
    await enterLocalMode();

    const session = await getSession();

    expect(session?.access_token).toBe('local.jwt.token');
    expect(session?.user.email).toBe('local-demo@localhost');
    expect(mockAuth.getSession).not.toHaveBeenCalled();
  });

  it('signOut clears the local session', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: 'local.jwt.token',
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          user: { id: 'demo-user', email: 'local-demo@localhost', created_at: '2026-01-01T00:00:00Z' },
        }),
        { status: 200 },
      ),
    );
    await enterLocalMode();
    expect(await getAccessToken()).toBe('local.jwt.token');

    await signOut();

    expect(await getAccessToken()).toBeNull();
  });

  it('onAuthStateChange fires when Local Mode starts', async () => {
    (fetch as unknown as ReturnType<typeof vi.fn>).mockResolvedValue(
      new Response(
        JSON.stringify({
          access_token: 'local.jwt.token',
          expires_at: Math.floor(Date.now() / 1000) + 3600,
          user: { id: 'demo-user', email: 'local-demo@localhost', created_at: '2026-01-01T00:00:00Z' },
        }),
        { status: 200 },
      ),
    );

    const handler = vi.fn();
    const stop = onAuthStateChange(handler);

    await enterLocalMode();

    expect(handler).toHaveBeenCalledWith(
      expect.objectContaining({ id: 'demo-user', email: 'local-demo@localhost' }),
    );
    stop();
  });
});
