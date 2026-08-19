import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

/**
 * Task 4 (Assign + My Tasks): MyTasksView exercises the real cross-project
 * path - Browser -> View -> GET /api/findings/my-tasks -> FindingService -
 * via a mocked `authFetch` at the transport boundary, same pattern
 * Findings.test.tsx uses.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

import { MyTasksView } from '../features/findings/MyTasksView';

const TASK_A = {
  id: '33333333-3333-3333-3333-333333333333',
  project_id: '22222222-2222-2222-2222-222222222222',
  project_name: 'Portal A',
  scan_run_id: null,
  fingerprint: 'abc123',
  rule_id: 'no_https',
  category: 'no_https',
  title: 'Missing HTTPS',
  evidence: 'Plain HTTP used.',
  impact: 'Traffic is unencrypted.',
  remediation: 'Enforce HTTPS redirects.',
  severity: 'medium',
  status: 'open',
  target: 'http://example.com',
  cve_id: null,
  assignee_user_id: 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb',
  deadline: null,
  is_overdue: false,
  verification_notes: '',
  resolution_reason: null,
  first_seen_scan_run_id: null,
  last_seen_scan_run_id: null,
  closed_at: null,
  created_at: '2026-08-01T09:00:00+00:00',
  updated_at: '2026-08-01T09:00:00+00:00',
};

const TASK_B = {
  ...TASK_A,
  id: '44444444-4444-4444-4444-444444444444',
  project_id: '55555555-5555-5555-5555-555555555555',
  project_name: 'Portal B',
  title: 'SQL injection',
  severity: 'critical',
  is_overdue: true,
};

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function listResponse(items: unknown[]) {
  return jsonResponse({ items, total: items.length, page: 1, page_size: 20 });
}

beforeEach(() => {
  authFetchMock.mockReset();
});

describe('My Tasks View — real backend', () => {
  it('shows an empty state when the caller has no assignments', async () => {
    authFetchMock.mockImplementation(() => listResponse([]));

    render(
      <MemoryRouter>
        <MyTasksView />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId('my-tasks-empty')).toBeInTheDocument());
  });

  it('lists cross-project tasks with project name, severity, and overdue badge', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/my-tasks')) return listResponse([TASK_A, TASK_B]);
      return listResponse([]);
    });

    render(
      <MemoryRouter>
        <MyTasksView />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId(`my-task-row-${TASK_A.id}`)).toBeInTheDocument());
    expect(screen.getByText('Portal A')).toBeInTheDocument();
    expect(screen.getByText('Portal B')).toBeInTheDocument();
    expect(screen.getByText('Missing HTTPS')).toBeInTheDocument();
    expect(screen.getByText('SQL injection')).toBeInTheDocument();
    expect(screen.getByTestId(`my-task-overdue-badge-${TASK_B.id}`)).toBeInTheDocument();
    expect(screen.queryByTestId(`my-task-overdue-badge-${TASK_A.id}`)).not.toBeInTheDocument();
  });

  it('toggling overdue-only re-fetches with overdue=true', async () => {
    authFetchMock.mockImplementation(() => listResponse([TASK_A]));

    render(
      <MemoryRouter>
        <MyTasksView />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId(`my-task-row-${TASK_A.id}`)).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('my-tasks-overdue-toggle'));

    await waitFor(() =>
      expect(
        authFetchMock.mock.calls.some(([url]) => String(url).includes('overdue=true')),
      ).toBe(true),
    );
  });
});
