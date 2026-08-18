import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

/**
 * Phase 3.3: GET /api/tools/scan-history/{id} previously had no frontend
 * caller despite exposing a real `details` field (findings/recommendations
 * for url_scan, source/cached for cve_lookup) not present in the list
 * response. This test renders the real ScanHistoryView and asserts clicking
 * "View" fetches and displays that detail data - it fails if the view
 * reverts to only ever calling the list endpoint.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

import { ScanHistoryView } from '../features/security-toolkit/scan-history/views/ScanHistoryView';

function listResponse() {
  return new Response(
    JSON.stringify({
      items: [
        {
          id: 'scan-1',
          scan_type: 'url_scan',
          target: 'https://example.test/marker',
          status: 'completed',
          risk_score: 5,
          severity: 'low',
          summary: 'safe (risk 5)',
          actor: 'anonymous',
          created_at: '2026-08-05T10:00:00+00:00',
        },
      ],
      total: 1,
      page: 1,
      page_size: 10,
    }),
    { status: 200 },
  );
}

function detailResponse() {
  return new Response(
    JSON.stringify({
      id: 'scan-1',
      scan_type: 'url_scan',
      target: 'https://example.test/marker',
      status: 'completed',
      risk_score: 5,
      severity: 'low',
      summary: 'safe (risk 5)',
      actor: 'anonymous',
      created_at: '2026-08-05T10:00:00+00:00',
      details: {
        findings: [{ code: 'http_error_status', message: 'The target responded with HTTP 404.', severity: 'low' }],
        recommendations: ['Continue to apply normal caution.'],
      },
    }),
    { status: 200 },
  );
}

describe('Scan History detail view', () => {
  it('fetches and renders the real detail endpoint when "View" is clicked', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (url.includes('/api/tools/scan-history/scan-1')) return Promise.resolve(detailResponse());
      return Promise.resolve(listResponse());
    });

    render(<MemoryRouter><ScanHistoryView /></MemoryRouter>);

    await waitFor(() => expect(screen.getAllByText('https://example.test/marker').length).toBeGreaterThan(0));

    fireEvent.click(screen.getByTitle('Xem chi tiết'));

    await waitFor(() =>
      expect(screen.getByText('The target responded with HTTP 404.')).toBeTruthy(),
    );
    expect(screen.getByText('Continue to apply normal caution.')).toBeTruthy();
    expect(
      authFetchMock.mock.calls.some(([url]) => String(url).includes('/api/tools/scan-history/scan-1')),
    ).toBe(true);
  });

  it('shows a retryable error state when the detail fetch fails', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (url.includes('/api/tools/scan-history/scan-1')) {
        return Promise.resolve(
          new Response(JSON.stringify({ error: 'not_found', message: 'Record not found.' }), { status: 404 }),
        );
      }
      return Promise.resolve(listResponse());
    });

    render(<MemoryRouter><ScanHistoryView /></MemoryRouter>);
    await waitFor(() => expect(screen.getAllByText('https://example.test/marker').length).toBeGreaterThan(0));
    fireEvent.click(screen.getByTitle('Xem chi tiết'));

    await waitFor(() => expect(screen.getByText('Record not found.')).toBeTruthy());
    expect(screen.getByText('Thử lại')).toBeTruthy();
  });
});
