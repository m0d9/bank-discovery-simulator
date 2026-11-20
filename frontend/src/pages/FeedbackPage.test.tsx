import { screen, waitFor } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { session } from '../test/fixtures';
import { renderApp } from '../test/render';
import { apiError, server } from '../test/server';

describe('FeedbackPage', () => {
  it('shows the placeholder until the coach arrives, and a way to start again', async () => {
    server.use(
      http.get('/api/sessions/:sessionId', () =>
        HttpResponse.json(session({ status: 'wrapped_up' })),
      ),
    );
    await renderApp('/feedback/s1', { language: 'ar' });
    expect(
      await screen.findByRole('heading', { level: 1, name: 'ملاحظات على مقابلتك مع سارة التجريبية' }),
    ).toBeInTheDocument();
    expect(screen.getByText(/ستظهر هنا ملاحظات المدرّب الافتراضي/)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: 'إجراء مقابلة مع عميل آخر' })).toHaveAttribute('href', '/');
  });

  it('offers to start again when the session no longer exists', async () => {
    server.use(http.get('/api/sessions/:sessionId', () => apiError('SESSION_NOT_FOUND', 404)));
    await renderApp('/feedback/gone');
    expect(await screen.findByRole('link', { name: 'Start again' })).toHaveAttribute('href', '/');
  });

  it('sends a session that is still being interviewed back to the interview', async () => {
    const { router } = await renderApp('/feedback/s1');
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/interview/s1');
    });
  });
});
