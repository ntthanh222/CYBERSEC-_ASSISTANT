import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import React from 'react';

/**
 * Task 7 (Admin Console Upgrade): the four new admin views exercise the
 * real backend path - View -> GET/POST /api/admin/* -> a mocked
 * `authFetch` at the transport boundary, same pattern MyTasks.test.tsx and
 * Findings.test.tsx already use.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

import { AdminWorkspacesView } from '../features/admin/views/AdminWorkspacesView';
import { AdminProjectsView } from '../features/admin/views/AdminProjectsView';
import { AdminFindingsView } from '../features/admin/views/AdminFindingsView';
import { AdminSlaPoliciesView } from '../features/admin/views/AdminSlaPoliciesView';

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function pageResponse(items: unknown[]) {
  return jsonResponse({ items, total: items.length, page: 1, page_size: 25 });
}

beforeEach(() => {
  authFetchMock.mockReset();
});

const WORKSPACE = {
  id: '11111111-1111-1111-1111-111111111111',
  name: 'Acme Corp Security',
  description: 'Primary org workspace.',
  created_by_user_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  member_count: 3,
  project_count: 2,
  created_at: '2026-08-01T09:00:00+00:00',
  updated_at: '2026-08-01T09:00:00+00:00',
};

const PROJECT = {
  id: '22222222-2222-2222-2222-222222222222',
  workspace_id: WORKSPACE.id,
  name: 'Customer Portal',
  domain: 'portal.acme.com',
  environment: 'production',
  criticality: 'critical',
  internet_facing: true,
  technologies: [],
  status: 'active',
  archived_at: null,
  owner_user_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  member_count: 4,
  open_findings_count: 7,
  created_at: '2026-08-01T09:00:00+00:00',
  updated_at: '2026-08-01T09:00:00+00:00',
};

const FINDING = {
  id: '33333333-3333-3333-3333-333333333333',
  project_id: PROJECT.id,
  project_name: PROJECT.name,
  scan_run_id: null,
  fingerprint: 'abc123',
  rule_id: 'sqli',
  category: 'injection',
  title: 'SQL injection in login form',
  evidence: 'payload reflected',
  impact: 'Full DB read access',
  remediation: 'Use parameterized queries',
  severity: 'critical',
  status: 'open',
  target: 'https://portal.acme.com/login',
  cve_id: null,
  assignee_user_id: null,
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

const SLA_POLICY = (severity: string, hours: number) => ({
  id: `${severity}-policy`,
  project_id: null,
  severity,
  hours_to_deadline: hours,
  created_at: '2026-08-01T09:00:00+00:00',
  updated_at: '2026-08-01T09:00:00+00:00',
});

describe('AdminWorkspacesView — real backend', () => {
  it('lists every workspace with member/project counts', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/api/admin/workspaces')) return pageResponse([WORKSPACE]);
      return pageResponse([]);
    });

    render(
      <MemoryRouter>
        <AdminWorkspacesView />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId(`admin-workspace-row-${WORKSPACE.id}`)).toBeInTheDocument());
    expect(screen.getByText('Acme Corp Security')).toBeInTheDocument();
    expect(screen.getByText('3')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
  });
});

describe('AdminProjectsView — real backend', () => {
  it('lists every project and archives one on click', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const href = String(url);
      if (href.includes('/archive') && init?.method === 'POST') {
        return jsonResponse({ ...PROJECT, status: 'archived', archived_at: '2026-08-10T00:00:00+00:00' });
      }
      if (href.includes('/api/admin/projects')) return pageResponse([PROJECT]);
      return pageResponse([]);
    });

    render(
      <MemoryRouter>
        <AdminProjectsView />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId(`admin-project-row-${PROJECT.id}`)).toBeInTheDocument());
    expect(screen.getByText('Customer Portal')).toBeInTheDocument();
    expect(screen.getByText('7')).toBeInTheDocument(); // open_findings_count

    fireEvent.click(screen.getByRole('button', { name: /archive/i }));

    await waitFor(() =>
      expect(
        authFetchMock.mock.calls.some(
          ([url, init]) => String(url).includes(`/api/admin/projects/${PROJECT.id}/archive`) && (init as RequestInit)?.method === 'POST',
        ),
      ).toBe(true),
    );
  });
});

describe('AdminFindingsView — real backend', () => {
  it('defaults to the Open view and switches presets on tab click', async () => {
    authFetchMock.mockImplementation(() => pageResponse([FINDING]));

    render(
      <MemoryRouter>
        <AdminFindingsView />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId(`admin-finding-row-${FINDING.id}`)).toBeInTheDocument());
    expect(
      authFetchMock.mock.calls.some(([url]) => String(url).includes('status=open')),
    ).toBe(true);

    fireEvent.click(screen.getByTestId('admin-findings-view-critical'));

    await waitFor(() =>
      expect(
        authFetchMock.mock.calls.some(([url]) => String(url).includes('severity=critical')),
      ).toBe(true),
    );
  });

  it('Fixed This Week tab requests the preset param', async () => {
    authFetchMock.mockImplementation(() => pageResponse([]));

    render(
      <MemoryRouter>
        <AdminFindingsView />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId('admin-findings-view-fixed_this_week')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('admin-findings-view-fixed_this_week'));

    await waitFor(() =>
      expect(
        authFetchMock.mock.calls.some(([url]) => String(url).includes('preset=fixed_this_week')),
      ).toBe(true),
    );
  });
});

describe('AdminSlaPoliciesView — real backend', () => {
  it('loads global default SLA policies and saves an edit', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const href = String(url);
      if (href.includes('/api/admin/sla-policies/critical') && init?.method === 'PATCH') {
        return jsonResponse(SLA_POLICY('critical', 24));
      }
      if (href.includes('/api/admin/sla-policies')) {
        return jsonResponse([
          SLA_POLICY('critical', 48),
          SLA_POLICY('high', 96),
          SLA_POLICY('medium', 240),
        ]);
      }
      return jsonResponse([]);
    });

    render(
      <MemoryRouter>
        <AdminSlaPoliciesView />
      </MemoryRouter>,
    );

    await waitFor(() => expect(screen.getByTestId('admin-sla-row-critical')).toBeInTheDocument());
    expect(screen.getByTestId('admin-sla-row-low')).toHaveTextContent('No default set yet');

    const criticalRow = screen.getByTestId('admin-sla-row-critical');
    const input = criticalRow.querySelector('input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: '24' } });
    fireEvent.click(within(criticalRow).getByRole('button', { name: /save/i }));

    await waitFor(() =>
      expect(
        authFetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).includes('/api/admin/sla-policies/critical') &&
            (init as RequestInit)?.method === 'PATCH',
        ),
      ).toBe(true),
    );
  });
});
