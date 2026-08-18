import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import React from 'react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import { AIAssistantView } from '../features/assistant/views/AIAssistantView';
import { URLScannerView } from '../features/security-toolkit/url-scanner/views/URLScannerView';
import { PasswordCheckerView } from '../features/security-toolkit/password-checker/views/PasswordCheckerView';
import { CVELookupView } from '../features/security-toolkit/cve-lookup/views/CVELookupView';
import { ScanHistoryView } from '../features/security-toolkit/scan-history/views/ScanHistoryView';

// These five Phase 2 screens now call the real FastAPI backend (via
// frontend/src/lib/api/*, which goes through authFetch) instead of
// FixtureDataProvider. Mocking authFetch here is the boundary: everything
// above it (the screens, the api/* modules) runs unmocked and for real;
// only the actual network call is stood in for, exactly the same
// principle backend/tests/test_auth.py uses for the JWKS fetch.
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
  UnauthenticatedError: class UnauthenticatedError extends Error {},
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

const renderWithContext = (ui: React.ReactElement) => {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
};

beforeEach(() => {
  authFetchMock.mockReset();
});

describe('AI Security Assistant Workspace UI', () => {
  it('loads conversations from the real backend and renders the composer', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (url.includes('/api/chatbot/conversations') && !url.includes('/messages')) {
        return Promise.resolve(
          jsonResponse({
            items: [{ id: 'conv-1', title: 'Log4Shell triage', actor: null, created_at: '2026-07-30T00:00:00Z', updated_at: '2026-07-30T00:00:00Z' }],
            total: 1,
            page: 1,
            page_size: 20,
          }),
        );
      }
      if (url.includes('/messages')) {
        return Promise.resolve(jsonResponse({ items: [], total: 0, page: 1, page_size: 50 }));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    renderWithContext(<AIAssistantView />);

    expect(screen.getByText(/TRỢ LÝ AN TOÀN THÔNG TIN/i)).toBeInTheDocument();
    expect(await screen.findByText(/Log4Shell triage/i)).toBeInTheDocument();
    expect(authFetchMock).toHaveBeenCalled();
  });

  it('sends a chat message via the real chatbot API and renders the reply', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/chatbot/conversations') && !url.includes('/messages') && (!init || init.method === 'GET')) {
        return Promise.resolve(jsonResponse({ items: [], total: 0, page: 1, page_size: 20 }));
      }
      if (url.includes('/api/chatbot/chat')) {
        return Promise.resolve(
          jsonResponse({
            conversation_id: 'conv-new',
            message_id: 'msg-1',
            role: 'assistant',
            content: 'Local knowledge base answer.',
            provider: 'local',
            intent: 'general',
            created_at: '2026-07-30T00:00:00Z',
            request_id: 'req-1',
            metadata: {},
          }),
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    renderWithContext(<AIAssistantView />);

    const input = await screen.findByPlaceholderText(/Hỏi CyberSec Assistant/i);
    fireEvent.change(input, { target: { value: 'What is CVSS?' } });
    fireEvent.submit(input.closest('form')!);

    expect(await screen.findByText(/Local knowledge base answer\./i)).toBeInTheDocument();
    const chatCall = authFetchMock.mock.calls.find(([url]) => String(url).includes('/api/chatbot/chat'));
    expect(chatCall).toBeDefined();
    const requestBody = JSON.parse((chatCall![1] as RequestInit).body as string);
    expect(requestBody).not.toHaveProperty('user_id');
  });
});

describe('URL Scanner Workspace UI', () => {
  it('displays the form and scans a URL via the real backend', async () => {
    authFetchMock.mockResolvedValue(
      jsonResponse({
        id: 'scan-1',
        url: 'https://example.com',
        normalized_url: 'https://example.com',
        hostname: 'example.com',
        port: 443,
        scheme: 'https',
        has_https: true,
        reachable: true,
        status: 'safe',
        risk_score: 5,
        severity: 'low',
        http_status: 200,
        final_url: 'https://example.com',
        redirect_chain: [],
        redirect_count: 0,
        headers: {},
        body_truncated: false,
        failure_reason: null,
        findings: [],
        recommendations: [],
        reputation: {
          configured: false,
          status: 'not_configured',
          malicious: 0,
          suspicious: 0,
          harmless: 0,
          undetected: 0,
          permalink: null,
          error_category: 'NOT_CONFIGURED',
        },
        duration_ms: 120,
        created_at: '2026-07-30T00:00:00Z',
      }),
    );

    renderWithContext(<URLScannerView />);
    expect(screen.getByLabelText(/URL đích cần kiểm tra/i)).toBeInTheDocument();

    const input = screen.getByLabelText(/URL đích cần kiểm tra/i);
    fireEvent.change(input, { target: { value: 'https://example.com' } });
    fireEvent.click(screen.getByText(/^QUÉT$/));

    expect(await screen.findByText(/Kết quả phân tích/i)).toBeInTheDocument();
    const call = authFetchMock.mock.calls[0];
    expect(String(call[0])).toContain('/api/tools/url-scan');
    const body = JSON.parse((call[1] as RequestInit).body as string);
    expect(body).toEqual({ url: 'https://example.com' });
  });

  it('surfaces a 400 SSRF-block error from the real backend', async () => {
    authFetchMock.mockResolvedValue(
      jsonResponse({ error: 'blocked_target', message: 'That target is not allowed to be scanned.', request_id: 'r1' }, 400),
    );

    renderWithContext(<URLScannerView />);
    fireEvent.change(screen.getByLabelText(/URL đích cần kiểm tra/i), { target: { value: 'http://169.254.169.254' } });
    fireEvent.click(screen.getByText(/^QUÉT$/));

    expect(await screen.findByText(/not allowed to be scanned/i)).toBeInTheDocument();
  });
});

describe('Password Checker Workspace UI', () => {
  it('provides a secure password entry box with visibility hide/show controls', async () => {
    renderWithContext(<PasswordCheckerView />);
    const input = screen.getByLabelText(/Nhập mật khẩu/i);
    expect(input).toBeInTheDocument();
    expect(input).toHaveAttribute('type', 'password');

    const toggleBtn = screen.getByLabelText(/Hiện mật khẩu/i);
    fireEvent.click(toggleBtn);
    expect(input).toHaveAttribute('type', 'text');
  });

  it('sends the password to the real backend for analysis and renders the result', async () => {
    authFetchMock.mockResolvedValue(
      jsonResponse({
        strength: 'strong',
        score: 3,
        length: 12,
        entropy_bits: 60,
        crack_time: 'centuries',
        has_lowercase: true,
        has_uppercase: true,
        has_digits: true,
        has_special: false,
        character_classes: 3,
        longest_repeat_run: 1,
        longest_sequential_run: 1,
        has_repeated_block: false,
        is_common: false,
        warnings: [],
        recommendations: ['Add a special character.'],
      }),
    );

    renderWithContext(<PasswordCheckerView />);
    const input = screen.getByLabelText(/Nhập mật khẩu/i);
    fireEvent.change(input, { target: { value: 'Sec-P@ss123' } });

    await waitFor(() => expect(authFetchMock).toHaveBeenCalled());
    const call = authFetchMock.mock.calls[0];
    expect(String(call[0])).toContain('/api/tools/password-check');
    const body = JSON.parse((call[1] as RequestInit).body as string);
    expect(body).toEqual({ password: 'Sec-P@ss123' });

    expect(await screen.findByText(/centuries/i)).toBeInTheDocument();

    const resetBtn = screen.getByText(/ĐẶT LẠI/i);
    fireEvent.click(resetBtn);
    expect(input).toHaveValue('');
  });
});

describe('CVE Lookup Workspace UI', () => {
  it('searches CVEs via the real backend and renders results', async () => {
    authFetchMock.mockResolvedValue(
      jsonResponse({
        query: 'log4j',
        count: 1,
        results: [
          {
            cve_id: 'CVE-2021-44228',
            description: 'Apache Log4j2 JNDI features do not protect against attacker controlled LDAP.',
            published_at: '2021-12-10T00:00:00Z',
            modified_at: null,
            cvss_score: 10.0,
            severity: 'critical',
            vector: 'CVSS:3.1/AV:N/AC:L/PR:N/UI:N/S:C/C:H/I:H/A:H',
            affected_products: ['Apache Log4j'],
            references: ['https://nvd.nist.gov/vuln/detail/CVE-2021-44228'],
            source: 'nvd',
            cached: false,
            fetched_at: '2026-07-30T00:00:00Z',
          },
        ],
      }),
    );

    renderWithContext(<CVELookupView />);
    expect(screen.getByLabelText(/Tìm trong cơ sở dữ liệu/i)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Tìm trong cơ sở dữ liệu/i), { target: { value: 'log4j' } });

    expect(await screen.findAllByText(/CVE-2021-44228/i)).not.toHaveLength(0);
    const call = authFetchMock.mock.calls[0];
    expect(String(call[0])).toContain('/api/cves/search');
  });
});

describe('Scan History Workspace UI', () => {
  it('lists real scan history records from the backend', async () => {
    authFetchMock.mockResolvedValue(
      jsonResponse({
        items: [
          {
            id: 'rec-1',
            scan_type: 'url_scan',
            target: 'https://corporate-security-update.example.test',
            status: 'failed',
            risk_score: null,
            severity: null,
            summary: 'DNS resolution failed',
            details: null,
            actor: null,
            created_at: '2026-07-30T00:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 10,
      }),
    );

    renderWithContext(<ScanHistoryView />);
    expect(screen.getByLabelText(/Truy vấn đã ghi nhận/i)).toBeInTheDocument();

    await waitFor(() => {
      const rows = screen.getAllByText(/corporate-security-update/i);
      expect(rows.length).toBeGreaterThan(0);
    });
  });

  it('deletes a record via the real backend after confirmation', async () => {
    authFetchMock.mockImplementation((_url: string, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        return Promise.resolve(new Response(null, { status: 204 }));
      }
      return Promise.resolve(
        jsonResponse({
          items: [
            {
              id: 'rec-1',
              scan_type: 'url_scan',
              target: 'https://corporate-security-update.example.test',
              status: 'failed',
              risk_score: null,
              severity: null,
              summary: 'DNS resolution failed',
              details: null,
              actor: null,
              created_at: '2026-07-30T00:00:00Z',
            },
          ],
          total: 1,
          page: 1,
          page_size: 10,
        }),
      );
    });

    renderWithContext(<ScanHistoryView />);

    let deleteBtns: HTMLElement[] = [];
    await waitFor(() => {
      deleteBtns = screen.getAllByTitle(/Xóa bản ghi/i);
      expect(deleteBtns.length).toBeGreaterThan(0);
    });

    fireEvent.click(deleteBtns[0]);
    const dialog = screen.getByRole('dialog', { name: /Xác nhận xóa nhật ký/i });
    expect(dialog).toBeInTheDocument();

    const purgeBtn = within(dialog).getByText(/^XÓA NHẬT KÝ$/i);
    fireEvent.click(purgeBtn);

    await waitFor(() => {
      const deleteCall = authFetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'DELETE');
      expect(deleteCall).toBeDefined();
      expect(String(deleteCall![0])).toContain('/api/tools/scan-history/rec-1');
    });
  });

  it('cancels deletion without calling the backend', async () => {
    authFetchMock.mockResolvedValue(
      jsonResponse({
        items: [
          {
            id: 'rec-1',
            scan_type: 'url_scan',
            target: 'https://corporate-security-update.example.test',
            status: 'failed',
            risk_score: null,
            severity: null,
            summary: 'DNS resolution failed',
            details: null,
            actor: null,
            created_at: '2026-07-30T00:00:00Z',
          },
        ],
        total: 1,
        page: 1,
        page_size: 10,
      }),
    );

    renderWithContext(<ScanHistoryView />);

    let deleteBtns: HTMLElement[] = [];
    await waitFor(() => {
      deleteBtns = screen.getAllByTitle(/Xóa bản ghi/i);
      expect(deleteBtns.length).toBeGreaterThan(0);
    });
    fireEvent.click(deleteBtns[0]);

    const cancelBtn = screen.getByText(/HỦY/i);
    fireEvent.click(cancelBtn);
    expect(screen.queryByText(/Xác nhận xóa nhật ký/i)).not.toBeInTheDocument();

    const deleteCall = authFetchMock.mock.calls.find(([, init]) => (init as RequestInit)?.method === 'DELETE');
    expect(deleteCall).toBeUndefined();
  });
});
