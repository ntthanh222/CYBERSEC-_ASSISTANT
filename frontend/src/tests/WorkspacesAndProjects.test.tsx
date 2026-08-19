import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import React from 'react';

/**
 * Task 1 (vuln-lifecycle foundation): WorkspaceListView/ProjectListView
 * exercise the real path - Browser -> View -> GET /api/workspaces|/projects
 * -> ...Service -> Postgres - via a mocked `authFetch` at the transport
 * boundary, the same pattern AssetInventory.test.tsx uses.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

import { WorkspaceListView } from '../features/workspaces/WorkspaceListView';
import { ProjectListView } from '../features/projects/ProjectListView';
import { ProjectDetailView } from '../features/projects/ProjectDetailView';

const WORKSPACE_1 = {
  id: '11111111-1111-1111-1111-111111111111',
  name: 'Acme Corp Security',
  description: 'Primary org workspace.',
  created_by_user_id: 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa',
  created_at: '2026-08-01T09:00:00+00:00',
  updated_at: '2026-08-01T09:00:00+00:00',
};

const PROJECT_1 = {
  id: '22222222-2222-2222-2222-222222222222',
  workspace_id: WORKSPACE_1.id,
  name: 'Customer Portal',
  domain: 'portal.acme.com',
  environment: 'production',
  criticality: 'high',
  internet_facing: true,
  technologies: [{ name: 'Django', version: '4.2' }],
  status: 'active',
  archived_at: null,
  owner_user_id: WORKSPACE_1.created_by_user_id,
  created_at: '2026-08-01T09:00:00+00:00',
  updated_at: '2026-08-01T09:00:00+00:00',
};

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function listResponse(items: unknown[]) {
  return jsonResponse({ items, total: items.length, page: 1, page_size: 20 });
}

const renderWithRouter = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

const renderProjectDetail = (id: string) =>
  render(
    <MemoryRouter initialEntries={[`/projects/${id}`]}>
      <Routes>
        <Route path="/projects/:id" element={<ProjectDetailView />} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(() => {
  authFetchMock.mockReset();
});

describe('Workspace List View — real backend', () => {
  it('shows real fetched workspaces', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/api/workspaces')) return listResponse([WORKSPACE_1]);
      return listResponse([]);
    });

    renderWithRouter(<WorkspaceListView />);
    expect(screen.getByTestId('workspace-list-loading')).toBeInTheDocument();

    await waitFor(() =>
      expect(screen.getByTestId(`workspace-card-${WORKSPACE_1.id}`)).toBeInTheDocument(),
    );
    expect(screen.getByText('Acme Corp Security')).toBeInTheDocument();
  });

  it('shows a real empty state when there are zero workspaces', async () => {
    authFetchMock.mockImplementation(() => listResponse([]));
    renderWithRouter(<WorkspaceListView />);
    await waitFor(() => expect(screen.getByTestId('workspace-list-empty')).toBeInTheDocument());
  });

  it('shows a real error state when the fetch fails', async () => {
    authFetchMock.mockImplementation(() =>
      jsonResponse({ error: 'internal_error', message: 'Could not reach the database.' }, 500),
    );
    renderWithRouter(<WorkspaceListView />);
    await waitFor(() => expect(screen.getByTestId('workspace-list-error')).toBeInTheDocument());
    expect(screen.getByText('Could not reach the database.')).toBeInTheDocument();
  });
});

describe('Project List View — real backend', () => {
  it('shows real fetched projects with criticality/environment', async () => {
    authFetchMock.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/workspaces')) return listResponse([WORKSPACE_1]);
      if (u.includes('/api/projects')) return listResponse([PROJECT_1]);
      return listResponse([]);
    });

    renderWithRouter(<ProjectListView />);
    await waitFor(() =>
      expect(screen.getByTestId(`project-card-${PROJECT_1.id}`)).toBeInTheDocument(),
    );
    expect(screen.getByText('Customer Portal')).toBeInTheDocument();
    expect(screen.getByText('high')).toBeInTheDocument();
  });

  it('shows a real empty state when there are zero projects', async () => {
    authFetchMock.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/workspaces')) return listResponse([]);
      return listResponse([]);
    });
    renderWithRouter(<ProjectListView />);
    await waitFor(() => expect(screen.getByTestId('project-list-empty')).toBeInTheDocument());
  });
});

describe('Project Detail View — real backend', () => {
  it('renders the overview tab from real project data', async () => {
    authFetchMock.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes(`/api/projects/${PROJECT_1.id}/members`)) return listResponse([]);
      if (u.includes(`/api/projects/${PROJECT_1.id}`)) return jsonResponse(PROJECT_1);
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    renderProjectDetail(PROJECT_1.id);
    await waitFor(() => expect(screen.getByTestId('project-overview')).toBeInTheDocument());
    expect(screen.getByText('Customer Portal')).toBeInTheDocument();
  });

  it('switching to the Technologies tab lists real technology entries', async () => {
    authFetchMock.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes(`/api/projects/${PROJECT_1.id}/members`)) return listResponse([]);
      if (u.includes(`/api/projects/${PROJECT_1.id}`)) return jsonResponse(PROJECT_1);
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    renderProjectDetail(PROJECT_1.id);
    await waitFor(() => expect(screen.getByTestId('project-tab-technologies')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('project-tab-technologies'));
    await waitFor(() => expect(screen.getByTestId('project-technologies')).toBeInTheDocument());
    expect(screen.getByText(/Django @ 4.2/)).toBeInTheDocument();
  });

  it('shows the Security tab with a real (empty) finding list, never fabricated findings', async () => {
    authFetchMock.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes(`/api/projects/${PROJECT_1.id}/members`)) return listResponse([]);
      if (u.includes(`/api/projects/${PROJECT_1.id}/findings`)) return listResponse([]);
      if (u.includes(`/api/projects/${PROJECT_1.id}`)) return jsonResponse(PROJECT_1);
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    renderProjectDetail(PROJECT_1.id);
    await waitFor(() => expect(screen.getByTestId('project-tab-security')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('project-tab-security'));
    await waitFor(() => expect(screen.getByTestId('finding-list-empty')).toBeInTheDocument());
  });
});
