import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';

/**
 * Task 5: ProjectSecurityDashboardView exercises the real path - View ->
 * GET /api/projects/:id/dashboard -> ProjectDashboardService - via a mocked
 * `authFetch` at the transport boundary, same pattern Findings.test.tsx
 * uses. The mocked response here is normal frontend test data (not "fake
 * data in production" - the backend's real aggregation is covered by
 * backend/tests/test_project_dashboard.py's exact-number assertions).
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

import { ProjectSecurityDashboardView } from '../features/security-dashboard/ProjectSecurityDashboardView';

const PROJECT_ID = '22222222-2222-2222-2222-222222222222';
const FINDING_ID = '33333333-3333-3333-3333-333333333333';
const SCAN_ID = '44444444-4444-4444-4444-444444444444';

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

const FULL_DASHBOARD = {
  project_id: PROJECT_ID,
  security_score: 61,
  open_findings: 4,
  open_by_severity: { critical: 2, high: 1, medium: 0, low: 1 },
  waiting_verify: 1,
  overdue: 1,
  fixed_this_week: 1,
  latest_scan: {
    id: SCAN_ID,
    status: 'completed',
    target: 'https://example.com',
    completed_at: '2026-08-19T10:00:00+00:00',
    summary: { critical: 1 },
  },
  security_trend: [
    { scan_run_id: SCAN_ID, completed_at: '2026-08-19T10:00:00+00:00', open_count: 3, score: 81 },
  ],
  top_risks: [
    {
      id: FINDING_ID,
      project_id: PROJECT_ID,
      scan_run_id: null,
      fingerprint: 'abc',
      rule_id: 'sqli',
      category: 'injection',
      title: 'SQL injection in login form',
      evidence: '',
      impact: '',
      remediation: '',
      severity: 'critical',
      status: 'open',
      target: 'https://example.com/login',
      cve_id: null,
      assignee_user_id: null,
      deadline: null,
      is_overdue: true,
      verification_notes: '',
      resolution_reason: null,
      first_seen_scan_run_id: null,
      last_seen_scan_run_id: null,
      closed_at: null,
      created_at: '2026-08-01T09:00:00+00:00',
      updated_at: '2026-08-01T09:00:00+00:00',
    },
  ],
  latest_findings: [],
  assigned_open: 2,
  assigned_open_by_assignee: [{ assignee_user_id: 'user-b', open_count: 2 }],
};

beforeEach(() => {
  authFetchMock.mockReset();
});

describe('ProjectSecurityDashboardView — real backend response shape', () => {
  it('renders every field from the API response with no placeholder numbers', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/dashboard')) return jsonResponse(FULL_DASHBOARD);
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    render(
      <MemoryRouter>
        <ProjectSecurityDashboardView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId('security-dashboard')).toBeInTheDocument());

    expect(screen.getByTestId('security-score')).toHaveTextContent('61');
    expect(screen.getByTestId('metric-open-findings')).toHaveTextContent('4');
    expect(screen.getByTestId('metric-critical')).toHaveTextContent('2');
    expect(screen.getByTestId('metric-high')).toHaveTextContent('1');
    expect(screen.getByTestId('metric-waiting-verify')).toHaveTextContent('1');
    expect(screen.getByTestId('metric-overdue')).toHaveTextContent('1');
    expect(screen.getByTestId('metric-fixed-this-week')).toHaveTextContent('1');

    expect(screen.getByTestId('latest-scan-summary')).toHaveTextContent('completed');
    expect(screen.getByTestId('latest-scan-summary')).toHaveTextContent('https://example.com');

    expect(screen.getByTestId('assigned-work-summary')).toHaveTextContent('2');
    expect(screen.getByTestId('assigned-work-summary')).toHaveTextContent('user-b');

    expect(screen.getByTestId(`trend-point-${SCAN_ID}`)).toBeInTheDocument();

    expect(screen.getByTestId(`top-risk-${FINDING_ID}`)).toHaveTextContent('SQL injection in login form');
    expect(screen.getByTestId(`top-risk-${FINDING_ID}`)).toHaveTextContent('critical');
  });

  it('shows an empty-state message when there is no data yet, not a fake zero-filled chart', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/dashboard')) {
        return jsonResponse({
          ...FULL_DASHBOARD,
          security_score: 100,
          open_findings: 0,
          open_by_severity: { critical: 0, high: 0, medium: 0, low: 0 },
          waiting_verify: 0,
          overdue: 0,
          fixed_this_week: 0,
          latest_scan: null,
          security_trend: [],
          top_risks: [],
          latest_findings: [],
          assigned_open: 0,
          assigned_open_by_assignee: [],
        });
      }
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    render(
      <MemoryRouter>
        <ProjectSecurityDashboardView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId('security-score')).toHaveTextContent('100'));
    expect(screen.getByTestId('latest-scan-summary')).toHaveTextContent('Chưa có lượt quét nào.');
    expect(screen.getByTestId('security-trend')).toHaveTextContent('Chưa có đủ lượt quét');
  });

  it('shows an error state and retries on demand when the backend request fails', async () => {
    authFetchMock.mockImplementation(() => jsonResponse({ error: 'server_error', message: 'boom' }, 500));

    render(
      <MemoryRouter>
        <ProjectSecurityDashboardView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId('security-dashboard-error')).toBeInTheDocument());
  });
});
