import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';

import { ForgotPasswordView } from '../features/auth/forgot-password/ForgotPasswordView';
import { ResetPasswordView } from '../features/auth/reset-password/ResetPasswordView';

/**
 * Functional-audit regression: these views used to claim a reset email was
 * "transmitted" / credentials were "updated" purely from a setTimeout, with
 * zero network call - an actively misleading fake-success UI. They must now
 * disclose honestly that the feature isn't implemented, and must never call
 * fetch.
 */
describe('Password recovery honesty (functional-audit fix)', () => {
  let fetchSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    fetchSpy = vi.spyOn(globalThis, 'fetch');
  });

  afterEach(() => {
    fetchSpy.mockRestore();
  });

  it('ForgotPasswordView is honest before AND after submit, and never calls fetch', () => {
    render(
      <MemoryRouter>
        <ForgotPasswordView />
      </MemoryRouter>,
    );

    // Pre-submit copy must not claim anything will be transmitted (Codex
    // round-1 finding: the old copy said "we will transmit a secure access
    // reset token" and showed "TRANSMITTING TOKEN..." mid-submit, which is
    // itself a fake in-progress action even though the final state was honest).
    expect(screen.getByText(/chưa được triển khai/i)).toBeTruthy();
    expect(screen.queryByText(/we will transmit/i)).toBeNull();

    fireEvent.change(screen.getByLabelText(/Email công ty đã đăng ký/i), {
      target: { value: 'auditor@example.test' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Tiếp tục/i }));

    expect(screen.getByText(/chưa khả dụng/i)).toBeTruthy();
    expect(screen.getByText(/Không có email nào được gửi/i)).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
  });

  it('ResetPasswordView is honest before AND after submit, and never calls fetch', () => {
    render(
      <MemoryRouter>
        <ResetPasswordView />
      </MemoryRouter>,
    );

    // Same round-1 finding, mirrored: pre-submit copy must not imply the
    // password will actually be saved, and there is no fake "UPDATING
    // CREDENTIALS..." in-progress state.
    expect(screen.getByText(/chưa được triển khai/i)).toBeTruthy();

    fireEvent.change(screen.getByLabelText(/Mật khẩu bảo mật mới/i), {
      target: { value: 'CorrectHorseBattery9!' },
    });
    fireEvent.change(screen.getByLabelText(/Xác nhận mật khẩu/i), {
      target: { value: 'CorrectHorseBattery9!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /Tiếp tục/i }));

    expect(screen.getByText(/chưa khả dụng/i)).toBeTruthy();
    expect(screen.getByText(/chưa thay đổi/i)).toBeTruthy();
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
