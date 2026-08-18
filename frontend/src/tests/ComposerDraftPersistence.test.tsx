import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

/**
 * Phase 3.4: a message typed but not yet sent must survive the
 * outage->recovery navigation cycle (which unmounts/remounts this
 * component), without ever being auto-submitted on the user's behalf.
 */
import { Composer } from '../features/assistant/components/Composer';

describe('Composer draft persistence', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('persists typed text to sessionStorage and restores it on remount', () => {
    const { unmount } = render(
      <Composer onSendMessage={vi.fn()} isGenerating={false} onStopGenerating={vi.fn()} />,
    );
    fireEvent.change(screen.getByPlaceholderText('Hỏi CyberSec Assistant...'), {
      target: { value: 'unsent draft message' },
    });
    expect(sessionStorage.getItem('cybersec_composer_draft')).toBe('unsent draft message');

    unmount();

    render(<Composer onSendMessage={vi.fn()} isGenerating={false} onStopGenerating={vi.fn()} />);
    expect(screen.getByPlaceholderText('Hỏi CyberSec Assistant...')).toHaveProperty(
      'value',
      'unsent draft message',
    );
  });

  it('clears the persisted draft once the message is actually sent, and never auto-sends it', () => {
    const onSendMessage = vi.fn();
    render(<Composer onSendMessage={onSendMessage} isGenerating={false} onStopGenerating={vi.fn()} />);
    const textarea = screen.getByPlaceholderText('Hỏi CyberSec Assistant...');
    fireEvent.change(textarea, { target: { value: 'send me' } });
    expect(sessionStorage.getItem('cybersec_composer_draft')).toBe('send me');

    // Mounting alone must never call onSendMessage - only an explicit submit does.
    expect(onSendMessage).not.toHaveBeenCalled();

    fireEvent.click(screen.getByTitle('Gửi tin nhắn'));
    expect(onSendMessage).toHaveBeenCalledWith('send me', 'fast');
    expect(sessionStorage.getItem('cybersec_composer_draft')).toBeNull();
  });
});
