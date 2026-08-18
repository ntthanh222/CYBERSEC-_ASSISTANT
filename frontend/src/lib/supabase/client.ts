import { createClient, type SupabaseClient } from '@supabase/supabase-js';

/**
 * Single Supabase client for the whole app. Uses the publishable
 * (anon-scoped) key only - by Supabase's own design this key is safe to
 * ship to a browser bundle. The secret/service-role key must never appear
 * in frontend code or environment variables prefixed VITE_ (Vite inlines
 * those into the built bundle).
 */
let client: SupabaseClient | null = null;

export function getSupabaseClient(): SupabaseClient {
  if (client) return client;

  const url = import.meta.env.VITE_SUPABASE_URL;
  const publishableKey = import.meta.env.VITE_SUPABASE_PUBLISHABLE_KEY;

  if (!url || !publishableKey) {
    throw new Error(
      'Supabase is not configured: set VITE_SUPABASE_URL and VITE_SUPABASE_PUBLISHABLE_KEY.',
    );
  }

  client = createClient(url, publishableKey, {
    auth: {
      persistSession: true,
      autoRefreshToken: true,
      detectSessionInUrl: true,
    },
  });
  return client;
}

/** Test-only: force a fresh client on the next call. */
export function _resetSupabaseClientForTests(): void {
  client = null;
}
