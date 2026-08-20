import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';

/**
 * Task 6 (CVE Risk Prioritization): ProjectCvePriorityView exercises the
 * real path - Browser -> View -> GET/POST /api/projects/:id/cve-assessments
 * -> ...Service - via a mocked `authFetch` at the transport boundary, same
 * pattern Findings.test.tsx uses.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

import { ProjectCvePriorityView } from '../features/cve-priority/ProjectCvePriorityView';

const PROJECT_ID = '22222222-2222-2222-2222-222222222222';
const ASSESSMENT_ID = '44444444-4444-4444-4444-444444444444';

const ASSESSMENT_PATCH_NOW = {
  id: ASSESSMENT_ID,
  project_id: PROJECT_ID,
  cve_id: 'CVE-2021-44228',
  cvss_score: 10.0,
  epss_score: 0.94427,
  is_kev: true,
  affected_version: '2.14.1',
  fixed_version: null,
  technology: null,
  priority: 'patch_now',
  score: 10.0,
  rationale: { reasoning: 'CISA KEV-listed AND internet-facing.' },
  finding_id: '55555555-5555-5555-5555-555555555555',
  created_at: '2026-08-01T09:00:00+00:00',
  updated_at: '2026-08-01T09:00:00+00:00',
};

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

beforeEach(() => {
  authFetchMock.mockReset();
});

describe('Project CVE Priority View — real backend', () => {
  it('shows an empty state when there are no assessments yet', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/cve-assessments')) return jsonResponse([]);
      return jsonResponse([]);
    });

    render(
      <MemoryRouter>
        <ProjectCvePriorityView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText('Chưa có đánh giá CVE nào cho dự án này.')).toBeInTheDocument(),
    );
  });

  it('lists an existing assessment with its priority badge', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/cve-assessments')) return jsonResponse([ASSESSMENT_PATCH_NOW]);
      return jsonResponse([]);
    });

    render(
      <MemoryRouter>
        <ProjectCvePriorityView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByTestId(`cve-assessment-row-CVE-2021-44228`)).toBeInTheDocument(),
    );
    const row = screen.getByTestId('cve-assessment-row-CVE-2021-44228');
    expect(row).toHaveTextContent('CVE-2021-44228');
    expect(row).toHaveTextContent('Vá ngay'); // patch_now label
    expect(row).toHaveTextContent('CÓ'); // is_kev = true
  });

  it('submitting the assessment form calls POST /cve-assessments and reloads the list', async () => {
    let posted = false;
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/cve-assessments') && init?.method === 'POST') {
        posted = true;
        return jsonResponse(ASSESSMENT_PATCH_NOW, 201);
      }
      if (u.includes('/cve-assessments')) {
        return jsonResponse(posted ? [ASSESSMENT_PATCH_NOW] : []);
      }
      return jsonResponse([]);
    });

    render(
      <MemoryRouter>
        <ProjectCvePriorityView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText('Chưa có đánh giá CVE nào cho dự án này.')).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByTestId('cve-priority-cve-id-input'), {
      target: { value: 'CVE-2021-44228' },
    });
    fireEvent.click(screen.getByTestId('cve-priority-assess-button'));

    await waitFor(() =>
      expect(
        authFetchMock.mock.calls.some(
          ([url, init]) =>
            String(url).includes(`/api/projects/${PROJECT_ID}/cve-assessments`) &&
            init?.method === 'POST',
        ),
      ).toBe(true),
    );
    await waitFor(() =>
      expect(screen.getByTestId('cve-assessment-row-CVE-2021-44228')).toBeInTheDocument(),
    );
  });

  it('shows a clear error when the backend rejects the assessment (insufficient role)', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/cve-assessments') && init?.method === 'POST') {
        return jsonResponse(
          { error: 'authorization_error', message: 'You do not have the required role on this project.' },
          403,
        );
      }
      if (u.includes('/cve-assessments')) return jsonResponse([]);
      return jsonResponse([]);
    });

    render(
      <MemoryRouter>
        <ProjectCvePriorityView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText('Chưa có đánh giá CVE nào cho dự án này.')).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByTestId('cve-priority-cve-id-input'), {
      target: { value: 'CVE-2021-44228' },
    });
    fireEvent.click(screen.getByTestId('cve-priority-assess-button'));

    await waitFor(() =>
      expect(screen.getByTestId('cve-priority-action-error')).toHaveTextContent(
        /required role/i,
      ),
    );
  });

  it('preview button fetches from the existing generic CVE lookup endpoint', async () => {
    authFetchMock.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes('/api/cves/CVE-2021-44228')) {
        return jsonResponse({
          cve_id: 'CVE-2021-44228',
          description: 'Log4Shell RCE.',
          published_at: null,
          modified_at: null,
          cvss_score: 10.0,
          severity: 'critical',
          vector: null,
          affected_products: [],
          references: [],
          source: 'nvd',
          cached: false,
          fetched_at: '2026-08-01T09:00:00+00:00',
        });
      }
      if (u.includes('/cve-assessments')) return jsonResponse([]);
      return jsonResponse([]);
    });

    render(
      <MemoryRouter>
        <ProjectCvePriorityView projectId={PROJECT_ID} />
      </MemoryRouter>,
    );

    await waitFor(() =>
      expect(screen.getByText('Chưa có đánh giá CVE nào cho dự án này.')).toBeInTheDocument(),
    );

    fireEvent.change(screen.getByTestId('cve-priority-cve-id-input'), {
      target: { value: 'CVE-2021-44228' },
    });
    fireEvent.click(screen.getByTestId('cve-priority-preview-button'));

    await waitFor(() => expect(screen.getByTestId('cve-priority-preview')).toBeInTheDocument());
    expect(screen.getByTestId('cve-priority-preview')).toHaveTextContent('CVSS: 10');
    // Confirms the preview hit /api/cves (the existing generic lookup), not
    // the project-scoped assessment endpoint.
    expect(
      authFetchMock.mock.calls.some(([url]) => String(url).includes('/api/cves/CVE-2021-44228')),
    ).toBe(true);
  });
});
