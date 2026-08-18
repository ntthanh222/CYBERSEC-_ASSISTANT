import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import '@testing-library/jest-dom';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import React from 'react';

/**
 * Task #5 (Assets vertical slice): AssetInventoryView/AssetProfileView used
 * to render `mockAssets` from a fixture as if it were real data. This test
 * exercises the real path - Browser -> AssetInventoryView -> GET/POST
 * /api/assets -> AssetService -> Postgres - via a mocked `authFetch` at the
 * transport boundary, the same pattern ScanHistoryDetail.test.tsx uses.
 */
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
}));

import { AssetInventoryView } from '../features/assets/views/AssetInventoryView';
import { AssetProfileView } from '../features/assets/views/AssetProfileView';

const ASSET_1 = {
  id: '11111111-1111-1111-1111-111111111111',
  name: 'Core Finance DB Server',
  type: 'database',
  hostname: 'fin-db-prod.internal',
  ip_address: '10.100.20.14',
  operating_system: 'RHEL 8.6',
  owner: 'Finance Dept',
  department: 'Finance',
  business_criticality: 'critical',
  internet_exposed: false,
  description: 'Main production database.',
  linked_cves: ['CVE-2021-44228'],
  patch_status: 'in_progress',
  exploit_evidence: 'unconfirmed',
  created_at: '2026-08-01T09:00:00+00:00',
  updated_at: '2026-08-01T09:00:00+00:00',
};

const ASSET_2 = {
  ...ASSET_1,
  id: '22222222-2222-2222-2222-222222222222',
  name: 'Customer Portal Gateway',
  type: 'server',
  hostname: 'portal.internal',
  linked_cves: [],
};

function jsonResponse(body: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(body), { status }));
}

function listResponse(items: unknown[]) {
  return jsonResponse({ items, total: items.length, page: 1, page_size: 50 });
}

const renderWithRouter = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

const renderProfile = (id: string) =>
  render(
    <MemoryRouter initialEntries={[`/assets/${id}`]}>
      <Routes>
        <Route path="/assets/:id" element={<AssetProfileView />} />
      </Routes>
    </MemoryRouter>,
  );

beforeEach(() => {
  authFetchMock.mockReset();
});

describe('Asset Inventory View — real backend', () => {
  it('shows a loading state, then real fetched assets', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes('/api/assets')) return listResponse([ASSET_1, ASSET_2]);
      return listResponse([]);
    });

    renderWithRouter(<AssetInventoryView />);
    expect(screen.getByTestId('asset-inventory-loading')).toBeInTheDocument();

    await waitFor(() => expect(screen.getByTestId(`asset-row-${ASSET_1.id}`)).toBeInTheDocument());
    expect(screen.getByTestId(`asset-row-${ASSET_2.id}`)).toBeInTheDocument();
    expect(authFetchMock.mock.calls.some(([url]) => String(url).includes('/api/assets'))).toBe(true);
  });

  it('shows a real empty state with an "add first asset" action when there are zero assets', async () => {
    authFetchMock.mockImplementation(() => listResponse([]));
    renderWithRouter(<AssetInventoryView />);
    await waitFor(() => expect(screen.getByTestId('asset-inventory-empty')).toBeInTheDocument());
    expect(screen.getByText(/thêm tài sản đầu tiên/i)).toBeInTheDocument();
  });

  it('shows a retryable error state when the fetch fails', async () => {
    authFetchMock.mockImplementation(() =>
      jsonResponse({ error: 'internal_error', message: 'Could not reach the database.' }, 500),
    );
    renderWithRouter(<AssetInventoryView />);
    await waitFor(() => expect(screen.getByTestId('asset-inventory-error')).toBeInTheDocument());
    expect(screen.getByText('Could not reach the database.')).toBeInTheDocument();

    authFetchMock.mockImplementation(() => listResponse([ASSET_1]));
    fireEvent.click(screen.getByText('THỬ LẠI'));
    await waitFor(() => expect(screen.getByTestId(`asset-row-${ASSET_1.id}`)).toBeInTheDocument());
  });

  it('clicking a row opens the drawer with real linked CVE ids, not fabricated ones', async () => {
    authFetchMock.mockImplementation(() => listResponse([ASSET_1]));
    renderWithRouter(<AssetInventoryView />);
    await waitFor(() => expect(screen.getByTestId(`asset-row-${ASSET_1.id}`)).toBeInTheDocument());

    fireEvent.click(screen.getByTestId(`asset-row-${ASSET_1.id}`));
    expect(screen.getByTestId('asset-drawer')).toBeInTheDocument();
    expect(screen.getByText('CVE-2021-44228')).toBeInTheDocument();
  });

  it('creating an asset POSTs to /api/assets and refreshes the real list', async () => {
    let created = false;
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/api/assets') && init?.method === 'POST') {
        created = true;
        return jsonResponse(ASSET_2, 201);
      }
      if (u.includes('/api/assets')) return listResponse(created ? [ASSET_2] : []);
      return listResponse([]);
    });

    renderWithRouter(<AssetInventoryView />);
    await waitFor(() => expect(screen.getByTestId('asset-inventory-empty')).toBeInTheDocument());

    fireEvent.click(screen.getByTestId('add-asset-button'));
    expect(screen.getByTestId('asset-create-form')).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText('Tên *'), { target: { value: 'Customer Portal Gateway' } });
    fireEvent.change(screen.getByLabelText('Tên máy chủ *'), { target: { value: 'portal.internal' } });
    fireEvent.change(screen.getByLabelText('Địa chỉ IP *'), { target: { value: '10.0.0.5' } });
    fireEvent.change(screen.getByLabelText('Hệ điều hành *'), { target: { value: 'Ubuntu 22.04' } });
    fireEvent.change(screen.getByLabelText('Chủ sở hữu *'), { target: { value: 'IT Operations' } });
    fireEvent.change(screen.getByLabelText('Phòng ban *'), { target: { value: 'Infrastructure' } });
    fireEvent.click(screen.getByTestId('asset-create-submit'));

    await waitFor(() => expect(screen.getByTestId(`asset-row-${ASSET_2.id}`)).toBeInTheDocument());
    expect(
      authFetchMock.mock.calls.some(
        ([url, init]) => String(url).includes('/api/assets') && (init as RequestInit | undefined)?.method === 'POST',
      ),
    ).toBe(true);
  });

  it('shows the real backend error message when creation fails, never a fake success', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      const u = String(url);
      if (u.includes('/api/assets') && init?.method === 'POST') {
        return jsonResponse({ error: 'invalid_request', message: 'hostname is required.' }, 422);
      }
      return listResponse([]);
    });

    renderWithRouter(<AssetInventoryView />);
    await waitFor(() => expect(screen.getByTestId('asset-inventory-empty')).toBeInTheDocument());
    fireEvent.click(screen.getByTestId('add-asset-button'));
    fireEvent.change(screen.getByLabelText('Tên *'), { target: { value: 'Broken Host' } });
    fireEvent.change(screen.getByLabelText('Tên máy chủ *'), { target: { value: 'x' } });
    fireEvent.change(screen.getByLabelText('Địa chỉ IP *'), { target: { value: '10.0.0.9' } });
    fireEvent.change(screen.getByLabelText('Hệ điều hành *'), { target: { value: 'Linux' } });
    fireEvent.change(screen.getByLabelText('Chủ sở hữu *'), { target: { value: 'IT' } });
    fireEvent.change(screen.getByLabelText('Phòng ban *'), { target: { value: 'IT' } });
    fireEvent.click(screen.getByTestId('asset-create-submit'));

    await waitFor(() => expect(screen.getByTestId('asset-create-error')).toHaveTextContent('hostname is required.'));
    // The form must still be open - a failed create is never treated as success.
    expect(screen.getByTestId('asset-create-form')).toBeInTheDocument();
  });
});

describe('Asset Profile View — real backend', () => {
  it('fetches and renders one asset by id', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (String(url).includes(`/api/assets/${ASSET_1.id}`)) return jsonResponse(ASSET_1);
      if (String(url).includes('/api/cves/')) return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    renderProfile(ASSET_1.id);
    await waitFor(() => expect(screen.getByRole('heading', { level: 2 })).toHaveTextContent(ASSET_1.name));
    expect(screen.getAllByText(new RegExp(ASSET_1.hostname)).length).toBeGreaterThan(0);
  });

  it('shows a real not-found state for a nonexistent id (404), not a fixture fallback', async () => {
    authFetchMock.mockImplementation(() => jsonResponse({ error: 'not_found', message: 'Asset not found.' }, 404));
    renderProfile('99999999-9999-9999-9999-999999999999');
    await waitFor(() => expect(screen.getByText(/không tìm thấy tài sản/i)).toBeInTheDocument());
  });

  it('enriches linked CVE ids with a live GET /api/cves/{id} call', async () => {
    authFetchMock.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes(`/api/assets/${ASSET_1.id}`)) return jsonResponse(ASSET_1);
      if (u.includes('/api/cves/CVE-2021-44228')) {
        return jsonResponse({
          cve_id: 'CVE-2021-44228',
          description: 'Apache Log4j2 JNDI RCE.',
          published_at: '2021-12-10T00:00:00Z',
          modified_at: '2026-06-15T00:00:00Z',
          cvss_score: 10.0,
          severity: 'critical',
          vector: null,
          affected_products: [],
          references: [],
          source: 'nvd',
          cached: true,
          fetched_at: '2026-08-04T00:00:00Z',
        });
      }
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    renderProfile(ASSET_1.id);
    await waitFor(() => expect(screen.getByTestId('cve-detail-CVE-2021-44228')).toBeInTheDocument());
    expect(screen.getByText('10.0')).toBeInTheDocument();
    expect(
      authFetchMock.mock.calls.some(([url]) => String(url).includes('/api/cves/CVE-2021-44228')),
    ).toBe(true);
  });

  it('degrades a single failed CVE lookup to "details unavailable" instead of hiding or faking it', async () => {
    authFetchMock.mockImplementation((url: string) => {
      const u = String(url);
      if (u.includes(`/api/assets/${ASSET_1.id}`)) return jsonResponse(ASSET_1);
      if (u.includes('/api/cves/CVE-2021-44228')) {
        return jsonResponse({ error: 'upstream_error', message: 'NVD unreachable.' }, 502);
      }
      return jsonResponse({ error: 'not_found', message: 'not found' }, 404);
    });

    renderProfile(ASSET_1.id);
    await waitFor(() => expect(screen.getByTestId('cve-error-CVE-2021-44228')).toBeInTheDocument());
    expect(screen.getByText(/không có thông tin chi tiết/i)).toBeInTheDocument();
  });
});
