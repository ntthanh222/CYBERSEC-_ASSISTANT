import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import React from 'react';
import '@testing-library/jest-dom';
import { MemoryRouter } from 'react-router-dom';
import { AIAssistantView } from '../features/assistant/views/AIAssistantView';

// Same boundary as Phase2_6RAG.test.tsx: mock authFetch only, so the real
// AIAssistantView / lib/api/chatbot.ts code runs.
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

const SIDEBAR_OPEN_STORAGE_KEY = 'cybersec_ai_sidebar_open';

beforeEach(() => {
  authFetchMock.mockReset();
  authFetchMock.mockImplementation((url: string) => {
    if (url.includes('/api/chatbot/conversations')) {
      return Promise.resolve(jsonResponse({ items: [], total: 0, page: 1, page_size: 20 }));
    }
    return Promise.resolve(jsonResponse({}, 404));
  });
  localStorage.clear();
});

describe('AI workspace conversation panel collapse', () => {
  it('persists the collapsed state to localStorage and restores it on remount', async () => {
    const { unmount } = renderWithContext(<AIAssistantView />);
    await screen.findByPlaceholderText(/CyberSec Assistant/i);

    expect(screen.getByPlaceholderText(/Tìm trong lịch sử/i)).toBeInTheDocument();

    fireEvent.click(screen.getByTitle('Đóng thanh bên'));

    expect(screen.queryByPlaceholderText(/Tìm trong lịch sử/i)).not.toBeInTheDocument();
    expect(localStorage.getItem(SIDEBAR_OPEN_STORAGE_KEY)).toBe('false');

    unmount();

    renderWithContext(<AIAssistantView />);
    await screen.findByPlaceholderText(/CyberSec Assistant/i);

    // Regression: feature/chat-ux-redesign's isSidebarOpen was a plain
    // useState(true) with no persistence, so a refresh always reopened the
    // panel regardless of what the user chose.
    expect(screen.queryByPlaceholderText(/Tìm trong lịch sử/i)).not.toBeInTheDocument();
  });

  it('defaults to open when nothing is stored yet', async () => {
    renderWithContext(<AIAssistantView />);
    await screen.findByPlaceholderText(/CyberSec Assistant/i);

    expect(screen.getByPlaceholderText(/Tìm trong lịch sử/i)).toBeInTheDocument();
  });
});

describe('AI workspace composer mode selector', () => {
  it('keeps a visible border class on the active Fast/Deep mode button', async () => {
    renderWithContext(<AIAssistantView />);
    await screen.findByPlaceholderText(/CyberSec Assistant/i);

    const fastButton = screen.getByRole('button', { name: 'Fast' });
    const deepButton = screen.getByRole('button', { name: 'Deep' });

    // Regression: feature/chat-ux-redesign's active-state class list carried
    // `border-primary/20` (a border *color* utility) without the `border`
    // width utility, so Tailwind rendered a 0px border - the active mode
    // selector's border indicator silently stopped appearing.
    expect(fastButton.className).toMatch(/(^|\s)border(\s|$)/);

    fireEvent.click(deepButton);
    expect(deepButton.className).toMatch(/(^|\s)border(\s|$)/);
  });
});
