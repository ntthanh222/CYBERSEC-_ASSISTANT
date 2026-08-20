import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Routes, Route } from 'react-router-dom';

/**
 * Task 2 (vuln-lifecycle Scan -> Finding pipeline): FindingListView and
 * FindingDetailView exercise the real path - Browser -> View ->
 * GET/POST /api/projects/:id/{scans,findings} -> ...Service - via a mocked
 * `authFetch` at the transport boundary, same pattern
 * WorkspacesAndProjects.test.tsx uses.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

const CURRENT_USER_ID = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa';
vi.mock('../features/auth/AuthContext', () => ({
  useAuth: () => ({
    user: { id: CURRENT_USER_ID, email: 'owner@test.local', username: 'owner', role: 'user' },
    logout: vi.fn(),
  }),
}));

import { FindingListView } from '../features/findings/FindingListView';
import { FindingDetailView } from '../features/findings/FindingDetailView';

const PROJECT_ID = '22222222-2222-2222-2222-222222222222';
const FINDING_ID = '33333333-3333-3333-3333-333333333333';

const FINDING_OPEN = {
  id: FINDING_ID,
  project_id: PROJECT_ID,
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
  assignee_user_id: null,
  deadline: null,
  verification_notes: '',
  resolution_reason: null,
  first_seen_scan_run_id: null,
  last_seen_scan_run_id: null,
  closed_at: null,
  created_at: '2026-08-01T09:00:00+00:00',
  updated_at: '2026-08-01T09:00:00+00:00',
};

const OWNER_MEMBER = {
  id: 'member-1',
  project_id: PROJECT_ID,
  user_id: CURRENT_USER_ID,
  project_role: 'owner',
  created_at: '2026-08-01T09:00:00+00:00',
  updated_at: '2026-08-01T09:00:00+00:00',
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

describe('Finding List View — real backend', () => {
  it('shows an empty state and a Run Scan button when there are zero findings', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/findings')) return listResponse([]);
      return listResponse([]);
    });

    render(
      <MemoryRouter>
        <FindingListView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    expect(screen.getByTestId('run-scan-button')).toBeInTheDocument();
    await waitFor(() => expect(screen.getByTestId('finding-list-empty')).toBeInTheDocument());
  });

  it('lists real fetched findings with severity/status', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/findings')) return listResponse([FINDING_OPEN]);
      return listResponse([]);
    });

    render(
      <MemoryRouter>
        <FindingListView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId(`finding-row-${FINDING_ID}`)).toBeInTheDocument());
    expect(screen.getByText('Missing HTTPS')).toBeInTheDocument();
    const row = screen.getByTestId(`finding-row-${FINDING_ID}`);
    expect(row).toHaveTextContent('medium');
    expect(row).toHaveTextContent('open');
  });

  it('triggering a scan calls the trigger-scan endpoint and reloads findings', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/scans') && init?.method === 'POST') {
        return jsonResponse({
          id: 'scan-1',
          project_id: PROJECT_ID,
          triggered_by_user_id: CURRENT_USER_ID,
          scan_type: 'url_scan',
          target: 'https://example.com',
          status: 'completed',
          started_at: null,
          completed_at: null,
          summary: {},
          previous_scan_run_id: null,
          created_at: '2026-08-01T09:00:00+00:00',
          updated_at: '2026-08-01T09:00:00+00:00',
        });
      }
      if (u.includes('/findings')) return listResponse([]);
      return listResponse([]);
    });

    render(
      <MemoryRouter>
        <FindingListView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId('finding-list-empty')).toBeInTheDocument());
    fireEvent.change(screen.getByPlaceholderText('https://example.com'), {
      target: { value: 'https://example.com' },
    });
    fireEvent.click(screen.getByTestId('run-scan-button'));

    await waitFor(() =>
      expect(
        authFetchMock.mock.calls.some(
          ([url, init]) => String(url).includes(`/api/projects/${PROJECT_ID}/scans`) && init?.method === 'POST',
        ),
      ).toBe(true),
    );
  });
});

describe('Finding Detail View — real backend', () => {
  const renderDetail = () =>
    render(
      <MemoryRouter initialEntries={[`/projects/${PROJECT_ID}/findings/${FINDING_ID}`]}>
        <Routes>
          <Route path="/projects/:id/findings/:findingId" element={<FindingDetailView />} />
        </Routes>
      </MemoryRouter>,
    );

  it('renders finding detail and offers transitions allowed for an owner', async () => {
    authFetchMock.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/eligible-assignees')) return listResponse([]);
      if (u.includes('/members')) return listResponse([OWNER_MEMBER]);
      if (u.includes(`/findings/${FINDING_ID}`)) return jsonResponse(FINDING_OPEN);
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    renderDetail();
    await waitFor(() => expect(screen.getByTestId('finding-detail-view')).toBeInTheDocument());
    expect(screen.getByText('Missing HTTPS')).toBeInTheDocument();
    // open -> confirmed is an owner-eligible transition.
    expect(screen.getByTestId('transition-confirmed')).toBeInTheDocument();
  });

  it('a false_positive transition requires a reason before submitting', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/eligible-assignees')) return listResponse([]);
      if (u.includes('/members')) return listResponse([OWNER_MEMBER]);
      if (u.includes('/transition') && init?.method === 'POST') {
        const updated = { ...FINDING_OPEN, status: 'false_positive', resolution_reason: 'Benign.' };
        return jsonResponse(updated);
      }
      if (u.includes(`/findings/${FINDING_ID}`)) return jsonResponse(FINDING_OPEN);
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    renderDetail();
    await waitFor(() => expect(screen.getByTestId('transition-false_positive')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('transition-false_positive'));
    // Reason input appears; submit is disabled until a reason is typed.
    const confirmButton = await screen.findByText('XÁC NHẬN');
    expect(confirmButton).toBeDisabled();
  });

  it('an owner sees the assignee picker and can assign an eligible developer', async () => {
    const DEVELOPER_ID = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb';
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/eligible-assignees')) {
        return listResponse([{ user_id: DEVELOPER_ID, project_role: 'developer' }]);
      }
      if (u.includes('/members')) return listResponse([OWNER_MEMBER]);
      if (u.includes('/assignee') && init?.method === 'PATCH') {
        const updated = { ...FINDING_OPEN, assignee_user_id: DEVELOPER_ID };
        return jsonResponse(updated);
      }
      if (u.includes(`/findings/${FINDING_ID}`)) return jsonResponse(FINDING_OPEN);
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    renderDetail();
    await waitFor(() => expect(screen.getByTestId('assignee-select')).toBeInTheDocument());

    fireEvent.change(screen.getByTestId('assignee-select'), { target: { value: DEVELOPER_ID } });
    fireEvent.click(screen.getByTestId('assignee-save-button'));

    await waitFor(() =>
      expect(
        authFetchMock.mock.calls.some(
          ([url, init]) => String(url).includes('/assignee') && init?.method === 'PATCH',
        ),
      ).toBe(true),
    );
  });

  it('shows a clear error when the backend rejects an ineligible assignee', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/eligible-assignees')) return listResponse([]);
      if (u.includes('/members')) return listResponse([OWNER_MEMBER]);
      if (u.includes('/assignee') && init?.method === 'PATCH') {
        return jsonResponse(
          { error: 'invalid_assignee', message: 'The target user is not an eligible assignee for this project.' },
          422,
        );
      }
      if (u.includes(`/findings/${FINDING_ID}`)) return jsonResponse(FINDING_OPEN);
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    renderDetail();
    await waitFor(() => expect(screen.getByTestId('assignee-select')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('assignee-save-button'));

    await waitFor(() =>
      expect(screen.getByText(/not an eligible assignee/i)).toBeInTheDocument(),
    );
  });
});
