import { render, screen, within } from '@testing-library/react';
import { describe, expect, it } from 'vitest';
import { type ChatMessage, ChatLog } from './ChatLog';

const messages: ChatMessage[] = [
  { n: 0, role: 'client', text: 'Hello, thanks for seeing me.' },
  { n: 1, role: 'student', text: 'How is business?' },
  { n: 2, role: 'client', text: 'نعم، العمل جيد. We are growing.' },
];

const speaker = (role: ChatMessage['role']) => (role === 'student' ? 'You said:' : 'Noura said:');

describe('ChatLog', () => {
  it('is a polite live log that announces only additions', () => {
    render(
      <>
        <h2 id="conversation">Conversation</h2>
        <ChatLog messages={messages} speakerLabel={speaker} labelledBy="conversation" />
      </>,
    );
    const log = screen.getByRole('log', { name: 'Conversation' });
    expect(log).toHaveAttribute('aria-live', 'polite');
    expect(log).toHaveAttribute('aria-relevant', 'additions');
  });

  it('gives every message a hidden speaker label, in order, opening line first', () => {
    render(<ChatLog messages={messages} speakerLabel={speaker} />);
    const items = within(screen.getByRole('log')).getAllByRole('listitem');
    expect(items.map((item) => item.textContent)).toEqual([
      'Noura said:Hello, thanks for seeing me.',
      'You said:How is business?',
      'Noura said:نعم، العمل جيد. We are growing.',
    ]);
    expect(screen.getAllByText('Noura said:')[0]).toHaveClass('sr-only');
    expect(screen.getByText('You said:')).toHaveClass('sr-only');
  });

  it('lets each message take its own direction, and gives each turn a focusable id', () => {
    render(<ChatLog messages={messages} speakerLabel={speaker} />);
    const mixed = screen.getByText('نعم، العمل جيد. We are growing.');
    expect(mixed).toHaveAttribute('dir', 'auto');
    const turn = document.getElementById('turn-2');
    expect(turn).toContainElement(mixed);
    expect(turn).toHaveAttribute('tabindex', '-1');
  });

  it("isn't live when kept for reference", () => {
    render(<ChatLog messages={messages} speakerLabel={speaker} live={false} />);
    expect(screen.queryByRole('log')).toBeNull();
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
  });
});
