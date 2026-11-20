import { act, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { OPENING, session, transcript } from '../test/fixtures';
import { setWideScreen } from '../test/media';
import { renderApp } from '../test/render';
import { apiError, fakeInterview, server } from '../test/server';
import { SLOW_REPLY_MS } from './useInterview';

const SLOW_LINE = 'The first reply can take up to 30 seconds while the model loads.';

async function messageBox() {
  return screen.findByRole('textbox', { name: 'Your message' });
}

describe('InterviewPage', () => {
  it('loads the transcript from the server (refresh-safe), with the opening line first', async () => {
    fakeInterview({ turns: transcript(2) });
    await renderApp('/interview/s1');
    const log = await screen.findByRole('log', { name: 'Conversation' });
    const messages = within(log).getAllByRole('listitem');
    expect(messages).toHaveLength(5);
    expect(messages[0]).toHaveTextContent(`Sara Test said:${OPENING}`);
    expect(messages[1]).toHaveTextContent('You said:Question 1?');
    expect(screen.getByText('Questions used: 2 of 30')).toBeInTheDocument();
    expect(document.title).toBe('Interview with Sara Test – Bank Client Discovery Simulator');
  });

  it("shows the session's models in the footer", async () => {
    fakeInterview();
    await renderApp('/interview/s1');
    await messageBox();
    const footer = screen.getByRole('contentinfo');
    await waitFor(() => {
      expect(footer).toHaveTextContent('Models in this session');
    });
    expect(footer).toHaveTextContent('AI clientclient-model');
  });

  describe('Composer', () => {
    it('sends on Enter, shows the reply, and keeps focus in the composer', async () => {
      const { sent } = fakeInterview();
      const { user } = await renderApp('/interview/s1');
      const box = await messageBox();
      await user.type(box, 'How is business?{Enter}');

      expect(await screen.findByText('Reply 1.')).toBeInTheDocument();
      expect(sent).toEqual(['How is business?']);
      expect(screen.getByText('How is business?')).toBeInTheDocument();
      expect(box).toHaveValue('');
      expect(box).toHaveFocus();
      expect(screen.getByText('Questions used: 1 of 30')).toBeInTheDocument();
    });

    it('adds a new line on Shift+Enter instead of sending', async () => {
      const { sent } = fakeInterview();
      const { user } = await renderApp('/interview/s1');
      const box = await messageBox();
      await user.type(box, 'Line one{Shift>}{Enter}{/Shift}Line two');
      expect(box).toHaveValue('Line one\nLine two');
      expect(sent).toEqual([]);
    });

    it('keeps the text after a failed send, and Retry resends exactly that text', async () => {
      const { sent } = fakeInterview();
      server.use(
        http.post('/api/sessions/:sessionId/messages', () => apiError('MODEL_UNAVAILABLE', 503), {
          once: true,
        }),
      );
      const { user } = await renderApp('/interview/s1');
      const box = await messageBox();
      await user.type(box, 'How is business?{Enter}');

      expect(await screen.findByRole('alert')).toHaveTextContent(
        "The AI model isn't available right now. Wait a moment, then try again.",
      );
      expect(box).toHaveValue('How is business?');
      // The message that failed is taken back out of the conversation.
      expect(within(screen.getByRole('log')).queryByText('How is business?')).toBeNull();

      await user.click(screen.getByRole('button', { name: 'Try again' }));
      expect(await screen.findByText('Reply 1.')).toBeInTheDocument();
      expect(sent).toEqual(['How is business?']);
      expect(screen.queryByRole('alert')).toBeNull();
      expect(box).toHaveFocus();
    });

    it('says when the server is unreachable, and keeps the text', async () => {
      fakeInterview();
      server.use(http.post('/api/sessions/:sessionId/messages', () => HttpResponse.error()));
      const { user } = await renderApp('/interview/s1');
      const box = await messageBox();
      await user.type(box, 'Hello?{Enter}');
      expect(await screen.findByRole('alert')).toHaveTextContent("We can't reach the server.");
      expect(box).toHaveValue('Hello?');
    });

    it('takes its limit from max_message_chars and does not send over it', async () => {
      const { sent } = fakeInterview({ overrides: { max_message_chars: 10 } });
      const { user } = await renderApp('/interview/s1');
      const box = await messageBox();
      expect(screen.getByText('Characters: 0 of 10')).toBeInTheDocument();

      await user.type(box, 'Twelve chars{Enter}');
      expect(screen.getByText('You have 2 characters too many.')).toBeInTheDocument();
      expect(box).toHaveAttribute('aria-invalid', 'true');
      expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled();
      expect(sent).toEqual([]);
    });

    it('locks at the turn limit and says why', async () => {
      fakeInterview({ turns: transcript(3), overrides: { max_student_turns: 3 } });
      await renderApp('/interview/s1');
      const box = await messageBox();
      expect(box).toBeDisabled();
      expect(box).toHaveAccessibleDescription(
        expect.stringContaining("You've used all your questions.") as string,
      );
    });
  });

  describe('End interview', () => {
    it('is disabled before 3 questions, and says why', async () => {
      fakeInterview({ turns: transcript(2) });
      const { user } = await renderApp('/interview/s1');
      await messageBox();
      const end = screen.getByRole('button', { name: 'End interview' });
      expect(end).toHaveAttribute('aria-disabled', 'true');
      expect(end).toHaveAccessibleDescription(
        'You can end the interview after asking at least 3 questions.',
      );
      await user.click(end);
      expect(screen.queryByRole('dialog')).toBeNull();
    });

    it('asks for confirmation in a dialog, then opens the wrap-up', async () => {
      fakeInterview({ turns: transcript(3) });
      const { router, user } = await renderApp('/interview/s1');
      await messageBox();
      const end = screen.getByRole('button', { name: 'End interview' });
      expect(end).not.toHaveAttribute('aria-disabled');

      await user.click(end);
      const dialog = screen.getByRole('dialog', { name: 'End the interview?' });
      await user.click(within(dialog).getByRole('button', { name: 'Keep interviewing' }));
      expect(screen.queryByRole('dialog')).toBeNull();
      expect(end).toHaveFocus();

      await user.click(end);
      await user.click(
        within(screen.getByRole('dialog')).getByRole('button', { name: 'End interview' }),
      );
      await waitFor(() => {
        expect(router.state.location.pathname).toBe('/wrapup/s1');
      });
    });
  });

  describe('typing status', () => {
    afterEach(() => {
      vi.useRealTimers();
    });

    it('says the client is typing, and adds a line in the same region when the reply is slow', async () => {
      vi.useFakeTimers({ toFake: ['setTimeout', 'clearTimeout'], shouldAdvanceTime: true });
      let release: () => void = () => undefined;
      const held = new Promise<void>((resolve) => {
        release = resolve;
      });
      fakeInterview({ beforeReply: () => held });
      const { user } = await renderApp('/interview/s1');
      await user.type(await messageBox(), 'Hello{Enter}');

      const typing = await screen.findByText('Sara Test is typing…');
      expect(screen.queryByText(SLOW_LINE)).toBeNull();
      act(() => {
        vi.advanceTimersByTime(SLOW_REPLY_MS);
      });
      const slow = await screen.findByText(SLOW_LINE);
      expect(slow.closest('[role="status"]')).toBe(typing.closest('[role="status"]'));

      release();
      expect(await screen.findByText('Reply 1.')).toBeInTheDocument();
      expect(screen.queryByText(SLOW_LINE)).toBeNull();
      expect(screen.queryByText('Sara Test is typing…')).toBeNull();
    });
  });

  it('shows the note on Arabic replies only when the UI is in Arabic', async () => {
    fakeInterview();
    await renderApp('/interview/s1', { language: 'ar' });
    await screen.findByRole('textbox', { name: 'رسالتك' });
    expect(
      screen.getByText('ردود العميل الافتراضي باللغة العربية تجريبية، وقد تتفاوت جودتها.'),
    ).toBeInTheDocument();
  });

  it('has no Arabic note in English', async () => {
    fakeInterview();
    await renderApp('/interview/s1');
    await messageBox();
    expect(screen.queryByText(/Arabic replies are experimental/)).toBeNull();
  });

  it('offers to start again when the session no longer exists', async () => {
    server.use(http.get('/api/sessions/:sessionId', () => apiError('SESSION_NOT_FOUND', 404)));
    await renderApp('/interview/gone');
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'This interview is no longer available.',
    );
    expect(screen.getByRole('link', { name: 'Start again' })).toHaveAttribute('href', '/');
  });

  it('offers to start again when the session is lost mid-interview', async () => {
    fakeInterview();
    server.use(
      http.post('/api/sessions/:sessionId/messages', () => apiError('SESSION_NOT_FOUND', 404)),
    );
    const { user } = await renderApp('/interview/s1');
    await user.type(await messageBox(), 'Hello{Enter}');
    expect(await screen.findByRole('link', { name: 'Start again' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Try again' })).toBeNull();
    expect(screen.queryByRole('textbox')).toBeNull();
  });

  it('sends a wrapped-up session to the feedback page', async () => {
    server.use(
      http.get('/api/sessions/:sessionId', () =>
        HttpResponse.json(session({ status: 'wrapped_up' })),
      ),
    );
    const { router } = await renderApp('/interview/s1');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/feedback/s1');
    });
  });

  describe('catalogue', () => {
    it('folds into a <details> on narrow screens', async () => {
      fakeInterview();
      await renderApp('/interview/s1');
      await messageBox();
      const catalogue = screen.getByRole('region', { name: 'Product catalogue' });
      expect(catalogue.querySelector(':scope > details > summary')).toHaveTextContent(
        'Product catalogue',
      );
    });

    it('sits beside the chat on wide screens, each product a <details> with text badges', async () => {
      setWideScreen(true);
      fakeInterview();
      const { user } = await renderApp('/interview/s1');
      const catalogue = await screen.findByRole('region', { name: 'Product catalogue' });
      expect(within(catalogue).getByRole('heading', { level: 2 })).toHaveTextContent(
        'Product catalogue',
      );
      const murabaha = await within(catalogue).findByText('Test Murabaha');
      const item = murabaha.closest('details');
      expect(item).not.toBeNull();
      expect(within(item as HTMLElement).getByText('Sharia-compliant')).toBeInTheDocument();
      expect(within(catalogue).getByText('Interest-based')).toBeInTheDocument();

      await user.click(murabaha);
      expect(item).toHaveAttribute('open');
      expect(within(item as HTMLElement).getByText('Test Murabaha pricing (fictional)')).toBeVisible();
    });
  });
});
