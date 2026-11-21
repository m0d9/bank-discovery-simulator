import { act, screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import type { Health } from '../api/types';
import ar from '../locales/ar.json';
import en from '../locales/en.json';
import { health, healthDown, models } from '../test/fixtures';
import { renderApp } from '../test/render';
import { apiError, fakeInterview, server } from '../test/server';

/** Serves `answers` to /api/health in turn (the last one repeats) and counts the calls. */
function serveHealth(...answers: Health[]) {
  const calls = { count: 0 };
  server.use(
    http.get('/api/health', () => {
      const answer = answers[Math.min(calls.count, answers.length - 1)];
      calls.count += 1;
      return HttpResponse.json(answer);
    }),
  );
  return calls;
}

/** Lets a response that has arrived render, before checking that nothing appeared. */
async function settle() {
  await act(() => new Promise((resolve) => setTimeout(resolve, 20)));
}

function around(element: HTMLElement, selector: string): HTMLElement {
  const found = element.closest<HTMLElement>(selector);
  if (!found) throw new Error(`no ${selector} around the element`);
  return found;
}

describe('HealthBanner', () => {
  it('stays out of the way while the model is reachable', async () => {
    const calls = serveHealth(health());
    await renderApp('/nowhere');
    await waitFor(() => {
      expect(calls.count).toBe(1);
    });
    await settle();
    expect(screen.queryByText(en.health.down)).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: en.common.retry })).not.toBeInTheDocument();
  });

  it('says politely that the model is unreachable and what to check, with details folded away', async () => {
    serveHealth(healthDown());
    const { user } = await renderApp('/nowhere');

    const banner = around(await screen.findByText(en.health.down), '[role="status"]');
    expect(banner).toHaveTextContent(en.health.ENDPOINT_UNREACHABLE);
    expect(within(banner).getByRole('button', { name: en.common.retry })).toBeInTheDocument();
    const details = around(within(banner).getByText(en.health.details), 'details');
    expect(details).not.toHaveAttribute('open');

    await user.click(within(details).getByText(en.health.details));
    expect(details).toHaveAttribute('open');
    expect(details).toHaveTextContent(`${en.health.endpoint}localhost:11434${en.health.unreachable}`);
    expect(details).toHaveTextContent(`${en.common.modelRole.client}${models.client}${en.health.missing}`);
    const serverHint = within(details).getByText(/^Cannot reach the model endpoint/);
    expect(serverHint).toHaveAttribute('lang', 'en');
  });

  it('speaks Arabic in the Arabic UI', async () => {
    serveHealth(healthDown());
    await renderApp('/nowhere', { language: 'ar' });

    const banner = around(await screen.findByText(ar.health.down), '[role="status"]');
    expect(banner).toHaveTextContent(ar.health.ENDPOINT_UNREACHABLE);
    expect(within(banner).getByRole('button', { name: ar.common.retry })).toBeInTheDocument();
    expect(within(banner).getByText(ar.health.details)).toBeInTheDocument();
  });

  it('names a missing model when the endpoint is up but a model is not', async () => {
    const ok = health();
    serveHealth(
      health({
        status: 'degraded',
        models: { ...ok.models, coach: { name: models.coach, available: false } },
        hint: `Model ${models.coach} not found. Run: ollama pull ${models.coach}`,
        hint_code: 'MODEL_MISSING',
      }),
    );
    await renderApp('/nowhere');

    const banner = around(await screen.findByText(en.health.degraded), '[role="status"]');
    expect(banner).toHaveTextContent(en.health.MODEL_MISSING);
    expect(banner).toHaveTextContent(`${en.common.modelRole.coach}${models.coach}${en.health.missing}`);
    expect(banner).toHaveTextContent(`${en.common.modelRole.client}${models.client}${en.health.available}`);
  });

  it('Retry checks again, says so while it checks, and the banner goes once the model is back', async () => {
    let release: () => void = () => undefined;
    const held = new Promise<void>((resolve) => {
      release = resolve;
    });
    let calls = 0;
    server.use(
      http.get('/api/health', async () => {
        calls += 1;
        if (calls === 1) return HttpResponse.json(healthDown());
        await held;
        return HttpResponse.json(health());
      }),
    );
    const { user } = await renderApp('/nowhere');
    await screen.findByText(en.health.down);

    const retry = screen.getByRole('button', { name: en.common.retry });
    await user.click(retry);
    expect(retry).toHaveTextContent(en.health.checking);
    expect(retry).toHaveAttribute('aria-disabled', 'true');
    expect(retry).toHaveFocus();
    await user.click(retry);

    release();
    await waitFor(() => {
      expect(screen.queryByText(en.health.down)).not.toBeInTheDocument();
    });
    expect(calls).toBe(2);
  });

  it('checks again when a message fails because the model is unavailable', async () => {
    const calls = serveHealth(health(), healthDown());
    fakeInterview();
    server.use(
      http.post('/api/sessions/:sessionId/messages', () => apiError('MODEL_UNAVAILABLE', 503)),
    );
    const { user } = await renderApp('/interview/s1');
    const box = await screen.findByRole('textbox', { name: en.interview.messageLabel });
    await waitFor(() => {
      expect(calls.count).toBe(1);
    });
    expect(screen.queryByText(en.health.down)).not.toBeInTheDocument();

    await user.type(box, 'How is business?{Enter}');

    expect(await screen.findByText(en.health.down)).toBeInTheDocument();
    expect(calls.count).toBe(2);
  });

  it('shows nothing when the health check itself fails', async () => {
    let calls = 0;
    server.use(
      http.get('/api/health', () => {
        calls += 1;
        return HttpResponse.error();
      }),
    );
    await renderApp('/nowhere');
    await waitFor(() => {
      expect(calls).toBe(1);
    });
    await settle();
    expect(screen.queryByRole('button', { name: en.common.retry })).not.toBeInTheDocument();
  });
});
