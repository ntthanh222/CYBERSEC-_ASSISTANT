import React, { createContext, useContext, useState, useEffect, useRef } from 'react';
import type { User, UserRole } from '../../types/data-provider.types';
import {
  checkAdminSetupStatus,
  enterLocalMode as authEnterLocalMode,
  getSession,
  isSupabaseConfigured,
  loginLocalAccount,
  onAuthStateChange,
  setupLocalAdmin,
  signIn as supabaseSignIn,
  signOut as supabaseSignOut,
  signUp as supabaseSignUp,
} from '../../lib/supabase/authService';
import { getMe } from '../../lib/api/auth';
import type { User as SupabaseUser } from '@supabase/supabase-js';

interface AuthContextType {
  user: User | null;
  /** The single sign-in entry point for the unified `/login` form. Accepts
   * either an email (hosted Supabase deployments) or a local account
   * username (Docker-local deployments) - which backend actually gets
   * called is decided by `isSupabaseConfigured()`, never by the caller,
   * so there is exactly one sign-in path visible per deployment. */
  login: (identifier: string, password: string) => Promise<boolean>;
  register: (email: string, password: string) => Promise<boolean>;
  enterLocalMode: () => Promise<boolean>;
  loginLocal: (username: string, password: string) => Promise<boolean>;
  setupAdmin: (username: string, password: string) => Promise<boolean>;
  checkAdminSetupNeeded: () => Promise<boolean | null>;
  logout: () => Promise<void>;
  isLoading: boolean;
  errorMsg: string | null;
  infoMsg: string | null;
  clearError: () => void;
  triggerSessionExpired: () => void;
  isSessionExpired: boolean;
}

export const AuthContext = createContext<AuthContextType | undefined>(undefined);

/** The app-level role/active-state always comes from the backend
 * (`GET /api/auth/me`), read fresh from the database - never hardcoded and
 * never trusted from the Supabase/local-session token itself. If the lookup
 * fails (offline, backend down), the session still exists but is treated as
 * plain `user` rather than blocking sign-in entirely. */
async function toAppUser(supabaseUser: SupabaseUser): Promise<User> {
  let role: UserRole = 'user';
  try {
    const me = await getMe();
    role = me.role;
  } catch {
    // Fail closed on privilege, not on sign-in: an unreachable role lookup
    // must never itself grant admin, so the default stays 'user'.
  }
  return {
    id: supabaseUser.id,
    username: supabaseUser.email ?? supabaseUser.id,
    email: supabaseUser.email ?? '',
    role,
    status: 'active',
    created_at: supabaseUser.created_at,
  };
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [infoMsg, setInfoMsg] = useState<string | null>(null);
  const [isSessionExpired, setIsSessionExpired] = useState<boolean>(false);
  // Distinguishes "user clicked logout" from "the session died on its own"
  // (refresh failure, or authFetch signing out after a 401) so only the
  // latter surfaces the session-expired UI.
  const explicitLogoutRef = useRef(false);
  const hadUserRef = useRef(false);

  useEffect(() => {
    let cancelled = false;

    getSession()
      .then(async (session) => {
        if (cancelled) return;
        if (session?.user) {
          const appUser = await toAppUser(session.user);
          if (cancelled) return;
          setUser(appUser);
          hadUserRef.current = true;
        }
      })
      .catch(() => {
        // Supabase not configured, or the session could not be restored -
        // fail closed to signed-out rather than throwing at startup.
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });

    // onAuthStateChange() itself never throws when Supabase isn't
    // configured (no VITE_SUPABASE_URL/VITE_SUPABASE_PUBLISHABLE_KEY at
    // build time - the default for any deployment without an explicit
    // frontend/.env, since that file is gitignored, and always the case
    // for the Docker-local one-command stack): it still subscribes to
    // Local Mode session changes unconditionally and only touches the real
    // Supabase client when a hosted project is actually configured.
    const unsubscribe = onAuthStateChange((supabaseUser) => {
      if (supabaseUser) {
        toAppUser(supabaseUser).then((appUser) => {
          if (cancelled) return;
          setUser(appUser);
        });
        hadUserRef.current = true;
        setIsSessionExpired(false);
        return;
      }
      const wasUnexpected = hadUserRef.current && !explicitLogoutRef.current;
      setUser(null);
      hadUserRef.current = false;
      explicitLogoutRef.current = false;
      if (wasUnexpected) setIsSessionExpired(true);
    });

    return () => {
      cancelled = true;
      unsubscribe();
    };
  }, []);

  const login = async (identifier: string, password: string): Promise<boolean> => {
    setIsLoading(true);
    setErrorMsg(null);
    setInfoMsg(null);
    setIsSessionExpired(false);

    const result = isSupabaseConfigured()
      ? await supabaseSignIn(identifier, password)
      : await loginLocalAccount(identifier, password);
    if (!result.ok) {
      setErrorMsg(result.error ?? 'Invalid credentials.');
      setIsLoading(false);
      return false;
    }

    const session = await getSession();
    if (session?.user) {
      setUser(await toAppUser(session.user));
      hadUserRef.current = true;
    }
    setIsLoading(false);
    return true;
  };

  const enterLocalMode = async (): Promise<boolean> => {
    setIsLoading(true);
    setErrorMsg(null);
    setInfoMsg(null);
    setIsSessionExpired(false);

    const result = await authEnterLocalMode();
    if (!result.ok) {
      setErrorMsg(result.error ?? 'Local mode is not available.');
      setIsLoading(false);
      return false;
    }

    const session = await getSession();
    if (session?.user) {
      setUser(await toAppUser(session.user));
      hadUserRef.current = true;
    }
    setIsLoading(false);
    return true;
  };

  const loginLocal = async (username: string, password: string): Promise<boolean> => {
    setIsLoading(true);
    setErrorMsg(null);
    setInfoMsg(null);
    setIsSessionExpired(false);

    const result = await loginLocalAccount(username, password);
    if (!result.ok) {
      setErrorMsg(result.error ?? 'Invalid username or password.');
      setIsLoading(false);
      return false;
    }

    const session = await getSession();
    if (session?.user) {
      setUser(await toAppUser(session.user));
      hadUserRef.current = true;
    }
    setIsLoading(false);
    return true;
  };

  const setupAdmin = async (username: string, password: string): Promise<boolean> => {
    setIsLoading(true);
    setErrorMsg(null);
    setInfoMsg(null);
    setIsSessionExpired(false);

    const result = await setupLocalAdmin(username, password);
    if (!result.ok) {
      setErrorMsg(result.error ?? 'Admin setup failed.');
      setIsLoading(false);
      return false;
    }

    const session = await getSession();
    if (session?.user) {
      setUser(await toAppUser(session.user));
      hadUserRef.current = true;
    }
    setIsLoading(false);
    return true;
  };

  const checkAdminSetupNeeded = async (): Promise<boolean | null> => {
    const result = await checkAdminSetupStatus();
    if (!result.ok) return null;
    return result.adminExists === false;
  };

  const register = async (email: string, password: string): Promise<boolean> => {
    setIsLoading(true);
    setErrorMsg(null);
    setInfoMsg(null);

    const result = await supabaseSignUp(email, password);
    if (!result.ok) {
      setErrorMsg(result.error ?? 'Registration failed.');
      setIsLoading(false);
      return false;
    }

    const session = await getSession();
    if (session?.user) {
      // Email confirmation disabled on this project - signed in immediately.
      setUser(await toAppUser(session.user));
      hadUserRef.current = true;
    } else {
      setInfoMsg('Registration successful. Check your email to confirm your account, then log in.');
    }
    setIsLoading(false);
    return true;
  };

  const logout = async (): Promise<void> => {
    explicitLogoutRef.current = true;
    await supabaseSignOut();
    setUser(null);
    hadUserRef.current = false;
    setIsSessionExpired(false);
  };

  const clearError = () => {
    setErrorMsg(null);
    setInfoMsg(null);
  };

  const triggerSessionExpired = () => {
    explicitLogoutRef.current = false;
    hadUserRef.current = true;
    setUser(null);
    setIsSessionExpired(true);
  };

  return (
    <AuthContext.Provider value={{
      user,
      login,
      register,
      enterLocalMode,
      loginLocal,
      setupAdmin,
      checkAdminSetupNeeded,
      logout,
      isLoading,
      errorMsg,
      infoMsg,
      clearError,
      triggerSessionExpired,
      isSessionExpired
    }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
