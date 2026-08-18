import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { ErrorBoundary } from '../components/ErrorBoundary';

function Bomb(): never {
  throw new Error('deliberate render crash for the test');
}

describe('ErrorBoundary', () => {
  it('renders the real 500 page instead of crashing the whole app', () => {
    // A real render exception logs to console.error by design (React itself
    // also logs it) - silence it here so the test output stays readable.
    vi.spyOn(console, 'error').mockImplementation(() => {});

    render(
      <MemoryRouter>
        <ErrorBoundary>
          <Bomb />
        </ErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByText('Đã xảy ra sự cố')).toBeTruthy();
    expect(screen.getByText(/Lỗi 500/i)).toBeTruthy();
  });

  it('renders children normally when nothing throws', () => {
    render(
      <MemoryRouter>
        <ErrorBoundary>
          <div>normal content</div>
        </ErrorBoundary>
      </MemoryRouter>,
    );

    expect(screen.getByText('normal content')).toBeTruthy();
  });
});
