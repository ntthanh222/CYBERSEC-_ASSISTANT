import type { Session, User } from '@supabase/supabase-js';
import { getSupabaseClient } from './client';

export interface AuthResult {
  ok: boolean;
  error?: string;
}

const LOCAL_SESSION_KEY = 'cybersec_local_session';
const LOCAL_SESSION_EVENT = 'cybersec-local-session-changed';

interface LocalSessionUser {
  id: string;
  email: string;
  created_at: string;
}

interface LocalSession {
  access_token: string;
  expires_at: number; // unix seconds
  user: LocalSessionUser;
}

/** Whether this deployment has a hosted Supabase project configured. This is
 * a build-time deployment property, not a user choice - exactly one of the
 * two sign-in backends is ever reachable in a given deployment, which is
 * what lets the single `/login` form stay a single visible form: it always
 * submits to the one backend that's actually live here. */
export function isSupabaseConfigured(): boolean {
  return Boolean(
    import.meta.env.VITE_SUPABASE_URL && import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY,
  );
}

function readLocalSession(): LocalSession | null {
  try {
    const raw = localStorage.getItem(LOCAL_SESSION_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LocalSession;
    if (!parsed?.access_token || !parsed?.expires_at || !parsed?.user) return null;
    if (parsed.expires_at * 1000 <= Date.now()) {
      localStorage.removeItem(LOCAL_SESSION_KEY);
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

function toSupabaseShapedSession(local: LocalSession): Session {
  const nowSeconds = Math.floor(Date.now() / 1000);
  return {
    access_token: local.access_token,
    token_type: 'bearer',
    expires_in: Math.max(0, local.expires_at - nowSeconds),
    expires_at: local.expires_at,
    refresh_token: '',
    user: {
      id: local.user.id,
      aud: 'authenticated',
      role: 'authenticated',
      email: local.user.email,
      app_metadata: {},
      user_metadata: {},
      created_at: local.user.created_at,
    },
  } as unknown as Session;
}

/**
 * Docker-local demo mode ("Local Mode"): mints a backend-verifiable session
 * with no hosted Supabase project, no manual token minting, and no
 * `frontend/.env`. The backend endpoint itself 404s outside
 * `APP_ENV=local`, so this silently fails (returns `ok: false`) in any
 * deployment where it isn't meant to work - it never fakes success.
 */
export async function enterLocalMode(): Promise<AuthResult> {
  try {
    const response = await fetch('/api/auth/local-session', { method: 'POST' });
    if (!response.ok) {
      return { ok: false, error: 'Chế độ cục bộ không khả dụng trên triển khai này.' };
    }
    const data = (await response.json()) as {
      access_token: string;
      expires_at: number;
      user: LocalSessionUser;
    };
    const session: LocalSession = {
      access_token: data.access_token,
      expires_at: data.expires_at,
      user: data.user,
    };
    localStorage.setItem(LOCAL_SESSION_KEY, JSON.stringify(session));
    window.dispatchEvent(new Event(LOCAL_SESSION_EVENT));
    return { ok: true };
  } catch {
    return { ok: false, error: 'Chế độ cục bộ hiện không khả dụng.' };
  }
}

interface AdminSessionPayload {
  access_token: string;
  expires_at: number;
  user: LocalSessionUser;
}

function storeLocalSession(data: AdminSessionPayload): void {
  const session: LocalSession = {
    access_token: data.access_token,
    expires_at: data.expires_at,
    user: data.user,
  };
  localStorage.setItem(LOCAL_SESSION_KEY, JSON.stringify(session));
  window.dispatchEvent(new Event(LOCAL_SESSION_EVENT));
}

/** Whether a local administrator account has already been bootstrapped. */
export async function checkAdminSetupStatus(): Promise<{ ok: boolean; adminExists?: boolean }> {
  try {
    const response = await fetch('/api/auth/local-admin/setup-status');
    if (!response.ok) return { ok: false };
    const data = (await response.json()) as { admin_exists: boolean };
    return { ok: true, adminExists: data.admin_exists };
  } catch {
    return { ok: false };
  }
}

/** First-run local admin bootstrap. Only succeeds once - a second call
 * returns `ok: false` with the backend's 409 message. */
export async function setupLocalAdmin(username: string, password: string): Promise<AuthResult> {
  try {
    const response = await fetch('/api/auth/local-admin/setup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      return { ok: false, error: body?.message ?? 'Thiết lập quản trị viên thất bại.' };
    }
    storeLocalSession(await response.json());
    return { ok: true };
  } catch {
    return { ok: false, error: 'Thiết lập quản trị viên hiện không khả dụng.' };
  }
}

/** Unified Local Mode password login - any role (demo_user, demo_analyst,
 * demo_superadmin, or a hand-created admin), not admin-only.
 * The account's actual role is decided server-side from the database, never
 * from anything this function sends. */
export async function loginLocalAccount(username: string, password: string): Promise<AuthResult> {
  try {
    const response = await fetch('/api/auth/local-login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      return { ok: false, error: body?.message ?? 'Tên đăng nhập hoặc mật khẩu không hợp lệ.' };
    }
    storeLocalSession(await response.json());
    return { ok: true };
  } catch {
    return { ok: false, error: 'Đăng nhập cục bộ hiện không khả dụng.' };
  }
}

/** Sign up a new user with email + password via Supabase Auth (GoTrue). */
export async function signUp(email: string, password: string): Promise<AuthResult> {
  if (!isSupabaseConfigured()) {
    return { ok: false, error: 'Đăng ký tài khoản không khả dụng trên triển khai này.' };
  }
  const { error } = await getSupabaseClient().auth.signUp({ email, password });
  return error ? { ok: false, error: error.message } : { ok: true };
}

/** Sign in an existing user. On success, Supabase persists the session
 * (localStorage by default) and future calls auto-refresh the access token. */
export async function signIn(email: string, password: string): Promise<AuthResult> {
  if (!isSupabaseConfigured()) {
    return { ok: false, error: 'Đăng nhập hệ thống lưu trữ chưa được cấu hình trên triển khai này.' };
  }
  const { error } = await getSupabaseClient().auth.signInWithPassword({ email, password });
  return error ? { ok: false, error: error.message } : { ok: true };
}

export async function signOut(): Promise<void> {
  localStorage.removeItem(LOCAL_SESSION_KEY);
  window.dispatchEvent(new Event(LOCAL_SESSION_EVENT));
  if (isSupabaseConfigured()) {
    await getSupabaseClient().auth.signOut();
  }
}

/** The current session, or null if signed out / never signed in. Checks the
 * Local Mode session first so a local demo session never has to touch a
 * (possibly unconfigured) Supabase client at all. */
export async function getSession(): Promise<Session | null> {
  const local = readLocalSession();
  if (local) return toSupabaseShapedSession(local);
  if (!isSupabaseConfigured()) return null;
  const { data } = await getSupabaseClient().auth.getSession();
  return data.session;
}

/**
 * The current access token to send as `Authorization: Bearer <token>`.
 *
 * Always goes through `getSession()` rather than a cached value - the
 * Supabase client refreshes the token in the background, and reading it
 * this way guarantees the caller never sends a token past its `exp`.
 */
export async function getAccessToken(): Promise<string | null> {
  const session = await getSession();
  return session?.access_token ?? null;
}

export type AuthChangeHandler = (user: User | null) => void;

/**
 * Subscribes to sign-in/sign-out/token-refresh events, covering both the
 * Local Mode session (a same-tab custom event, since there is no SDK
 * driving it) and, if configured, the real Supabase client.
 */
export function onAuthStateChange(handler: AuthChangeHandler): () => void {
  const localListener = () => {
    const local = readLocalSession();
    handler(local ? toSupabaseShapedSession(local).user : null);
  };
  window.addEventListener(LOCAL_SESSION_EVENT, localListener);
  window.addEventListener('storage', localListener);

  let unsubscribeSupabase = () => {};
  if (isSupabaseConfigured()) {
    const {
      data: { subscription },
    } = getSupabaseClient().auth.onAuthStateChange((_event, session) => {
      // A local session always wins - never let a stale/absent Supabase
      // event stomp on an active Local Mode session.
      if (readLocalSession()) return;
      handler(session?.user ?? null);
    });
    unsubscribeSupabase = () => subscription.unsubscribe();
  }

  return () => {
    window.removeEventListener(LOCAL_SESSION_EVENT, localListener);
    window.removeEventListener('storage', localListener);
    unsubscribeSupabase();
  };
}
