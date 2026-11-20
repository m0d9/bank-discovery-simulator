import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { useState } from 'react';
import { describe, expect, it, vi } from 'vitest';
import { countChars } from '../i18n/format';
import { Composer } from './Composer';

function Harness({
  onSubmit,
  sending = false,
  maxChars = 1000,
}: {
  onSubmit: (text: string) => void;
  sending?: boolean;
  maxChars?: number;
}) {
  const [value, setValue] = useState('');
  return (
    <Composer
      id="message"
      label="Your message"
      sendLabel="Send"
      value={value}
      onChange={setValue}
      onSubmit={() => {
        onSubmit(value);
      }}
      maxChars={maxChars}
      sending={sending}
    />
  );
}

describe('Composer', () => {
  it('sends on Enter', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);
    await user.type(screen.getByRole('textbox', { name: 'Your message' }), 'Hello{Enter}');
    expect(onSubmit).toHaveBeenCalledExactlyOnceWith('Hello');
  });

  it('adds a new line on Shift+Enter', async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);
    const box = screen.getByRole('textbox', { name: 'Your message' });
    await user.type(box, 'One{Shift>}{Enter}{/Shift}Two');
    expect(box).toHaveValue('One\nTwo');
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("doesn't send while an input method is composing", () => {
    const onSubmit = vi.fn();
    render(<Harness onSubmit={onSubmit} />);
    const box = screen.getByRole('textbox', { name: 'Your message' });
    fireEvent.change(box, { target: { value: 'مرحبا' } });
    fireEvent.keyDown(box, { key: 'Enter', isComposing: true });
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("doesn't send empty text", async () => {
    const onSubmit = vi.fn();
    const user = userEvent.setup();
    render(<Harness onSubmit={onSubmit} />);
    await user.type(screen.getByRole('textbox'), '   {Enter}');
    expect(onSubmit).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('is read-only while sending, so focus can stay in it', () => {
    render(<Harness onSubmit={vi.fn()} sending />);
    const box = screen.getByRole('textbox', { name: 'Your message' });
    expect(box).toHaveAttribute('readonly');
    expect(box).toHaveAttribute('aria-disabled', 'true');
    expect(box).toBeEnabled();
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
  });

  it('describes the field with its character count', async () => {
    const user = userEvent.setup();
    render(<Harness onSubmit={vi.fn()} maxChars={20} />);
    const box = screen.getByRole('textbox', { name: 'Your message' });
    await user.type(box, 'Hi');
    expect(box).toHaveAccessibleDescription('Characters: 2 of 20');
  });
});

describe('countChars', () => {
  it('counts as the server does: code points, without control characters, trimmed', () => {
    expect(countChars('  hi  ')).toBe(2);
    expect(countChars('a\u0007b')).toBe(2);
    expect(countChars('line\r\nnext')).toBe(9);
    expect(countChars('😀')).toBe(1);
    expect(countChars('مرحبا')).toBe(5);
  });
});
