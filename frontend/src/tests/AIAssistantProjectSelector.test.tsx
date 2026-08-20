import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import { AIAssistantView } from '../features/assistant/views/AIAssistantView';

// Task 8: AI Project Security Copilot - verifies the project selector wires
// the selected project's id into the chat request, and that no project_id
// is sent when nothing is selected (unchanged pre-Task-8 behavior).
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

const PROJECT = {
  id: 'proj-1',
  workspace_id: 'ws-1',
  name: 'Checkout Service',
  domain: null,
  environment: 'production',
  criticality: 'critical',
  internet_facing: true,
  technologies: [],
  status: 'active',
  archived_at: null,
  owner_user_id: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
};

const renderWithContext = (ui: React.ReactElement) => render(<MemoryRouter>{ui}</MemoryRouter>);

function chatResponseBody() {
  return {
    conversation_id: 'conv-1',
    message_id: 'msg-1',
    role: 'assistant',
    content: 'Đã nhận.',
    provider: 'local',
    intent: 'general',
    created_at: '2026-01-01T00:00:00Z',
    request_id: 'req-1',
    citations: [],
    metadata: { mode: 'fast', grounded: false },
  };
}

beforeEach(() => {
  authFetchMock.mockReset();
  localStorage.clear();
  authFetchMock.mockImplementation((url: string) => {
    if (url.includes('/api/chatbot/conversations')) {
      return Promise.resolve(jsonResponse({ items: [], total: 0, page: 1, page_size: 20 }));
    }
    if (url.includes('/api/projects')) {
      return Promise.resolve(jsonResponse({ items: [PROJECT], total: 1, page: 1, page_size: 100 }));
    }
    if (url.includes('/api/chatbot/chat')) {
      return Promise.resolve(jsonResponse(chatResponseBody()));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
});

describe('AI Assistant project selector', () => {
  it('sends no project_id when nothing is selected', async () => {
    renderWithContext(<AIAssistantView />);
    await screen.findByPlaceholderText(/CyberSec Assistant/i);

    fireEvent.change(screen.getByPlaceholderText('Hỏi CyberSec Assistant...'), {
      target: { value: 'What is SSRF?' },
    });
    fireEvent.click(screen.getByTitle('Gửi tin nhắn'));

    await waitFor(() => {
      const chatCall = authFetchMock.mock.calls.find(([url]) =>
        String(url).includes('/api/chatbot/chat'),
      );
      expect(chatCall).toBeTruthy();
      const body = JSON.parse((chatCall![1] as RequestInit).body as string);
      expect(body.project_id).toBeNull();
    });
  });

  it('wires the selected project id into the chat request', async () => {
    renderWithContext(<AIAssistantView />);
    await screen.findByPlaceholderText(/CyberSec Assistant/i);

    const picker = await screen.findByTestId('project-picker');
    fireEvent.change(picker, { target: { value: PROJECT.id } });

    fireEvent.change(screen.getByPlaceholderText('Hỏi CyberSec Assistant...'), {
      target: { value: 'Project này có vấn đề gì không?' },
    });
    fireEvent.click(screen.getByTitle('Gửi tin nhắn'));

    await waitFor(() => {
      const chatCall = authFetchMock.mock.calls.find(([url]) =>
        String(url).includes('/api/chatbot/chat'),
      );
      expect(chatCall).toBeTruthy();
      const body = JSON.parse((chatCall![1] as RequestInit).body as string);
      expect(body.project_id).toBe(PROJECT.id);
    });
  });
});
