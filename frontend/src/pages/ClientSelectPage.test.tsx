import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import { created, omar } from '../test/fixtures';
import { renderApp } from '../test/render';
import { apiError, server } from '../test/server';

describe('ClientSelectPage', () => {
  it('shows each client with a headline, text badges and one start button', async () => {
    await renderApp('/');
    const card = await screen.findByRole('article', { name: 'Sara Test' });
    expect(within(card).getByText('Runs a test bakery')).toBeInTheDocument();
    expect(within(card).getByText('Small business')).toBeInTheDocument();
    expect(within(card).getByText('Difficulty: Medium')).toBeInTheDocument();
    expect(within(card).getAllByRole('button')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Start interview with Omar Test' })).toBeInTheDocument();
    expect(document.title).toBe('Choose a client – Bank Client Discovery Simulator');
  });

  it('shows the cards in Arabic', async () => {
    await renderApp('/', { language: 'ar' });
    const card = await screen.findByRole('article', { name: 'سارة التجريبية' });
    expect(within(card).getByText('الشركات الصغيرة والمتوسطة')).toBeInTheDocument();
    expect(within(card).getByText('مستوى الصعوبة: متوسط')).toBeInTheDocument();
    expect(within(card).getByRole('button', { name: 'بدء المقابلة مع سارة التجريبية' })).toBeInTheDocument();
  });

  it('starts a session in the UI language and opens the interview', async () => {
    let body: unknown;
    server.use(
      http.post('/api/sessions', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(created(omar, 's42'), { status: 201 });
      }),
    );
    const { router, user } = await renderApp('/', { language: 'ar' });
    await user.click(await screen.findByRole('button', { name: 'بدء المقابلة مع عمر التجريبي' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/interview/s42');
    });
    expect(body).toEqual({ client_id: 'omar-test', language: 'ar' });
  });

  it('shows an error with Retry when the session cannot be created', async () => {
    server.use(http.post('/api/sessions', () => apiError('INTERNAL_ERROR', 500)));
    const { router, user } = await renderApp('/');
    await user.click(await screen.findByRole('button', { name: 'Start interview with Sara Test' }));
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Something went wrong on the server. Please try again.',
    );

    server.resetHandlers();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/interview/s1');
    });
  });

  it('explains a network failure while loading the clients, and retries', async () => {
    server.use(http.get('/api/clients', () => HttpResponse.error()));
    const { user } = await renderApp('/');
    expect(await screen.findByRole('alert')).toHaveTextContent("We can't reach the server.");

    server.resetHandlers();
    await user.click(screen.getByRole('button', { name: 'Try again' }));
    expect(await screen.findByRole('article', { name: 'Sara Test' })).toBeInTheDocument();
  });

  it('moves focus to the page heading after an in-app navigation', async () => {
    const { user } = await renderApp('/nowhere');
    await user.click(screen.getByRole('link', { name: 'Go to the client list' }));
    expect(await screen.findByRole('heading', { level: 1, name: 'Choose a client' })).toHaveFocus();
  });
});
