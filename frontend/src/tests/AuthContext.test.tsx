import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

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

import { _resetSupabaseClientForTests } from '../lib/supabase/client';
import { AuthProvider, useAuth } from '../features/auth/AuthContext';

function Probe() {
  const { isLoading, user } = useAuth();
  return <div>probe-rendered isLoading={String(isLoading)} user={String(user)}</div>;
}

describe('AuthProvider without Supabase configured', () => {
  beforeEach(() => {
    _resetSupabaseClientForTests();
    vi.stubEnv('VITE_SUPABASE_URL', '');
    vi.stubEnv('VITE_SUPABASE_PUBLISHABLE_KEY', '');
  });

  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it('renders children instead of crashing (fails closed to signed-out)', async () => {
    render(
      <MemoryRouter>
        <AuthProvider>
          <Probe />
        </AuthProvider>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText(/probe-rendered/)).toBeTruthy();
    });
    expect(screen.getByText(/isLoading=false/)).toBeTruthy();
    expect(screen.getByText(/user=null/)).toBeTruthy();
  });
});
