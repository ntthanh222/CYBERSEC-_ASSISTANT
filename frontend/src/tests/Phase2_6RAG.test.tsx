import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import { KnowledgeBaseView } from '../features/knowledge-base/views/KnowledgeBaseView';
import { AIAssistantView } from '../features/assistant/views/AIAssistantView';

// Same boundary as Phase2.test.tsx: mock authFetch only, so the real
// KnowledgeBaseView / lib/api/knowledge.ts / lib/api/chatbot.ts code runs.
const authFetchMock = vi.fn();
vi.mock('../lib/supabase/authFetch', () => ({
  authFetch: (...args: unknown[]) => authFetchMock(...args),
  UnauthenticatedError: class UnauthenticatedError extends Error {},
}));

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: status === 204 ? {} : { 'Content-Type': 'application/json' },
  });
}

const renderWithContext = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

beforeEach(() => {
  authFetchMock.mockReset();
});

const readyDoc = {
  id: 'doc-1',
  owner_user_id: 'user-a',
  title: 'Incident Response Runbook',
  source_type: 'upload',
  source_name: 'runbook.pdf',
  mime_type: 'application/pdf',
  processing_status: 'ready',
  error_message: null,
  page_count: 3,
  chunk_count: 5,
  created_at: '2026-07-30T00:00:00Z',
  updated_at: '2026-07-30T00:00:00Z',
};

const failedDoc = {
  ...readyDoc,
  id: 'doc-2',
  title: 'Bad Upload',
  processing_status: 'failed',
  error_message: 'The document has no extractable text content.',
  chunk_count: 0,
};

describe('Knowledge Base UI', () => {
  it('lists documents and renders processing status badges', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (url.includes('/api/knowledge/documents') && !url.includes('/documents/')) {
        return Promise.resolve(
          jsonResponse({ items: [readyDoc, failedDoc], total: 2, page: 1, page_size: 20 }),
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    renderWithContext(<KnowledgeBaseView />);

    expect(await screen.findByText('Incident Response Runbook')).toBeInTheDocument();
    expect(screen.getByText('Bad Upload')).toBeInTheDocument();
    expect(screen.getByText('SẴN SÀNG')).toBeInTheDocument();
    expect(screen.getByText('THẤT BẠI')).toBeInTheDocument();
    expect(screen.getByText(/no extractable text content/i)).toBeInTheDocument();
  });

  it('uploads a file via multipart form data and never sends an owner id', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/knowledge/documents') && init?.method === 'POST') {
        expect(init.body).toBeInstanceOf(FormData);
        const form = init.body as FormData;
        expect(form.get('owner_user_id')).toBeNull();
        expect(form.get('file')).toBeTruthy();
        return Promise.resolve(
          jsonResponse({ document: readyDoc, reused_existing: false }, 201),
        );
      }
      if (url.includes('/api/knowledge/documents')) {
        return Promise.resolve(jsonResponse({ items: [], total: 0, page: 1, page_size: 20 }));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    renderWithContext(<KnowledgeBaseView />);
    await screen.findByText(/Chưa có tài liệu nào được tải lên/i);

    const file = new File(['hello world'], 'notes.txt', { type: 'text/plain' });
    const input = document.getElementById('knowledge-upload-input') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await waitFor(() => {
      const uploadCall = authFetchMock.mock.calls.find(
        ([, init]) => (init as RequestInit | undefined)?.method === 'POST',
      );
      expect(uploadCall).toBeDefined();
    });
  });

  it('deletes a document after confirmation', async () => {
    let deleteCalled = false;
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/knowledge/documents') && init?.method === 'DELETE') {
        deleteCalled = true;
        return Promise.resolve(jsonResponse(null, 204));
      }
      if (url.includes('/api/knowledge/documents')) {
        return Promise.resolve(
          jsonResponse(
            { items: deleteCalled ? [] : [readyDoc], total: deleteCalled ? 0 : 1, page: 1, page_size: 20 },
          ),
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    renderWithContext(<KnowledgeBaseView />);
    await screen.findByText('Incident Response Runbook');

    fireEvent.click(screen.getByTitle('Xóa tài liệu'));
    expect(await screen.findByText(/Xác nhận xóa tài liệu/i)).toBeInTheDocument();
    fireEvent.click(screen.getByText('XÓA'));

    await waitFor(() => expect(deleteCalled).toBe(true));
  });

  it('reprocesses a document', async () => {
    authFetchMock.mockImplementation((url: string) => {
      if (url.includes('/reprocess')) {
        return Promise.resolve(jsonResponse(readyDoc));
      }
      if (url.includes('/api/knowledge/documents')) {
        return Promise.resolve(jsonResponse({ items: [readyDoc], total: 1, page: 1, page_size: 20 }));
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    renderWithContext(<KnowledgeBaseView />);
    await screen.findByText('Incident Response Runbook');
    fireEvent.click(screen.getByTitle('Xử lý lại (chia đoạn và tạo embedding lại)'));

    await waitFor(() => {
      const reprocessCall = authFetchMock.mock.calls.find(([url]) => String(url).includes('/reprocess'));
      expect(reprocessCall).toBeDefined();
    });
  });

  it('shows retrieval preview results and an empty state when nothing matches', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/knowledge/documents') && (!init || init.method === 'GET')) {
        return Promise.resolve(jsonResponse({ items: [], total: 0, page: 1, page_size: 20 }));
      }
      if (url.includes('/api/knowledge/retrieval/preview')) {
        return Promise.resolve(
          jsonResponse({
            query: 'ransomware containment',
            results: [
              {
                document_id: 'doc-1',
                document_title: 'Incident Response Runbook',
                chunk_id: 'chunk-1',
                chunk_index: 0,
                page: 3,
                heading: 'Containment',
                content: 'Isolate the affected host immediately.',
                score: 0.81,
              },
            ],
            retrieval_metadata: { result_count: 1 },
          }),
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    renderWithContext(<KnowledgeBaseView />);
    await screen.findByText(/Chưa có tài liệu nào được tải lên/i);

    const input = screen.getByPlaceholderText(/Nhập câu hỏi để xem chatbot sẽ truy xuất được gì/i);
    fireEvent.change(input, { target: { value: 'ransomware containment' } });
    fireEvent.click(screen.getByText('XEM TRƯỚC'));

    expect(await screen.findByText(/Isolate the affected host immediately\./i)).toBeInTheDocument();
    expect(screen.getByText(/81% khớp/i)).toBeInTheDocument();
  });

  it('catches UnauthenticatedError and renders the generic fallback error before unmounting', async () => {
    const { UnauthenticatedError } = await import('../lib/supabase/authFetch');
    authFetchMock.mockRejectedValue(new UnauthenticatedError());

    renderWithContext(<KnowledgeBaseView />);
    expect(await screen.findByText(/Không thể tải danh sách tài liệu/i)).toBeInTheDocument();
  });
});

describe('Chatbot RAG citations', () => {
  it('renders knowledge-base citations and a grounded/non-grounded distinction', async () => {
    authFetchMock.mockImplementation((url: string, init?: RequestInit) => {
      if (url.includes('/api/chatbot/conversations') && !url.includes('/messages') && (!init || init.method === 'GET')) {
        return Promise.resolve(jsonResponse({ items: [], total: 0, page: 1, page_size: 20 }));
      }
      if (url.includes('/api/chatbot/chat')) {
        return Promise.resolve(
          jsonResponse({
            conversation_id: 'conv-1',
            message_id: 'msg-1',
            role: 'assistant',
            content: 'Isolate the host and rotate credentials.',
            provider: 'local',
            intent: 'general',
            created_at: '2026-07-30T00:00:00Z',
            request_id: 'req-1',
            citations: [
              {
                marker: 1,
                document_id: 'doc-1',
                chunk_id: 'chunk-1',
                title: 'Incident Response Runbook',
                source: 'runbook.pdf',
                page: 3,
                heading: 'Containment',
                chunk_index: 0,
                score: 0.81,
              },
            ],
            metadata: { grounded: true },
          }),
        );
      }
      return Promise.resolve(jsonResponse({}, 404));
    });

    renderWithContext(<AIAssistantView />);
    const input = await screen.findByPlaceholderText(/Hỏi CyberSec Assistant/i);
    fireEvent.change(input, { target: { value: 'How do we contain ransomware?' } });
    fireEvent.submit(input.closest('form')!);

    expect(await screen.findByText(/Trích dẫn:/i)).toBeInTheDocument();
    const citationButton = screen.getByRole('button', { name: /Incident Response Runbook/i });
    expect(citationButton).toBeInTheDocument();
    // Page/heading metadata must stay visible on the citation chip itself, not
    // only in a hover-only tooltip (regression: feature/chat-ux-redesign
    // dropped this suffix when it condensed the citations row).
    expect(citationButton).toHaveTextContent(/p\.3/i);
    expect(citationButton).toHaveTextContent(/Containment/i);
    expect(screen.queryByText(/Không dựa trên Knowledge Base/i)).not.toBeInTheDocument();
  });
});
