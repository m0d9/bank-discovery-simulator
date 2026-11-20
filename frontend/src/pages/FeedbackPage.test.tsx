import { screen, waitFor, within } from '@testing-library/react';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import type { SessionPublic } from '../api/types';
import { created, feedback, sara, session, transcript } from '../test/fixtures';
import { renderApp } from '../test/render';
import { apiError, server } from '../test/server';

/** The value, or a clear test failure when it's missing. */
function present<T>(value: T | null | undefined): T {
  if (value === null || value === undefined) throw new Error('expected an element');
  return value;
}

/** The session is wrapped up, with three questions; feedback requests are recorded. */
function wrappedUp(overrides: Partial<SessionPublic> = {}) {
  const asked: string[] = [];
  server.use(
    http.get('/api/sessions/:sessionId', () =>
      HttpResponse.json(session({ status: 'wrapped_up', turns: transcript(3), ...overrides })),
    ),
    http.post('/api/sessions/:sessionId/feedback', ({ request }) => {
      asked.push(new URL(request.url).searchParams.get('lang') ?? '');
      return HttpResponse.json(feedback());
    }),
  );
  return { asked };
}

describe('FeedbackPage', () => {
  it('shows a calm message while the coach reviews the interview', async () => {
    wrappedUp();
    server.use(http.post('/api/sessions/:sessionId/feedback', () => new Promise<never>(() => {})));
    await renderApp('/feedback/s1');

    const status = await screen.findByText(/The coach is reviewing your interview/);
    expect(status.closest('[role="status"]')).toBeInTheDocument();
    expect(screen.getByText(/The first review can take up to a minute/)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { level: 2 })).not.toBeInTheDocument();
  });

  it('shows the discovery map, the verdicts and the six sections of feedback', async () => {
    wrappedUp();
    await renderApp('/feedback/s1');

    await screen.findByRole('heading', { level: 2, name: 'Discovery map' });
    expect(screen.getAllByRole('heading', { level: 2 }).map((h) => h.textContent)).toEqual([
      'Discovery map',
      'Your recommendations',
      'What went well',
      'What was missed',
      'How to improve',
      'About your summary',
    ]);
    expect(screen.getByText('Your feedback is ready.')).toBeInTheDocument();

    const map = screen.getByRole('table', { name: 'Discovery map' });
    const [, found, missed] = within(map).getAllByRole('row');
    expect(within(present(found)).getByRole('rowheader')).toHaveTextContent('Bridge the cash gap.');
    expect(found).toHaveTextContent('Uncovered');
    expect(within(present(found)).getByRole('link', { name: 'Turn 3' })).toBeInTheDocument();
    expect(found).toHaveTextContent('Question 2?');
    // `sharia` completed the need, and the overdraft pitch brought it out.
    expect(found).toHaveTextContent('In reaction to a product you proposed.');
    expect(missed).toHaveTextContent('Missed');
    expect(missed).toHaveTextContent('Not found');
    expect(screen.getByText('Needs uncovered').nextSibling).toHaveTextContent('1 of 2');

    const overdraft = present(screen.getByText('Test Overdraft').closest('li'));
    expect(overdraft).toHaveTextContent('Not suitable');
    // The same reason for two needs is shown once.
    expect(within(overdraft).getAllByText('Interest-based.')).toHaveLength(1);
    expect(overdraft).toHaveTextContent('Your reason: Flexible cash.');
    expect(screen.getByText('Test Account').closest('li')).toHaveTextContent(
      "This client's answer key doesn't mention this product.",
    );
    const opportunities = screen.getByRole('heading', {
      level: 3,
      name: "Suitable products you didn't recommend",
    }).nextElementSibling as HTMLElement;
    expect(within(opportunities).getByText('Test Murabaha')).toBeInTheDocument();
    expect(opportunities).toHaveTextContent('Meets:Bridge the cash gap.');

    expect(screen.getByText('A question you could have asked:').parentElement).toHaveTextContent(
      'Is Islamic banking important to you?',
    );
    expect(screen.getByText('For example:').parentElement).toHaveTextContent(
      'What matters to you in a bank?',
    );
    expect(screen.getByText('She is paid late and needs Islamic finance.')).toHaveAttribute(
      'dir',
      'auto',
    );
    expect(screen.getByText(/Your summary names the cash gap/)).toBeInTheDocument();
  });

  it('asks for the feedback in Arabic, and marks English-only content as English', async () => {
    const { asked } = wrappedUp();
    await renderApp('/feedback/s1', { language: 'ar' });

    await screen.findByRole('heading', { level: 2, name: 'خريطة الاكتشاف' });
    expect(asked).toEqual(['ar']);
    expect(screen.getByRole('rowheader', { name: 'سدّ الفجوة النقدية.' })).not.toHaveAttribute(
      'lang',
    );
    const englishOnly = within(screen.getByRole('rowheader', { name: 'Finance the stock.' }));
    expect(englishOnly.getByText('Finance the stock.')).toHaveAttribute('lang', 'en');
    expect(englishOnly.getByText('Finance the stock.')).toHaveAttribute('dir', 'ltr');
    expect(screen.getAllByText('لم يُكتشف').length).toBeGreaterThan(0);
    const overdraft = screen.getByText('سحب على المكشوف تجريبي').closest('li');
    expect(overdraft).toHaveTextContent('غير مناسب');
    expect(overdraft).toHaveTextContent('قائم على الفائدة.');
  });

  it('switching the language asks the coach again in that language', async () => {
    const { asked } = wrappedUp();
    const { user } = await renderApp('/feedback/s1');
    await screen.findByRole('heading', { level: 2, name: 'Discovery map' });

    await user.click(screen.getByRole('button', { name: 'العربية' }));

    await screen.findByRole('heading', { level: 2, name: 'خريطة الاكتشاف' });
    expect(asked).toEqual(['en', 'ar']);
  });

  it('an evidence link opens the transcript and moves focus to that turn', async () => {
    wrappedUp();
    const { user } = await renderApp('/feedback/s1');
    await screen.findByRole('heading', { level: 2, name: 'What was missed' });
    const transcriptBox = present(screen.getByText('Interview transcript').closest('details'));
    expect(transcriptBox).not.toHaveAttribute('open');

    const missed = present(screen.getByText(/You pitched an overdraft/).closest('li'));
    await user.click(within(missed).getByRole('link', { name: 'Turn 5' }));

    expect(transcriptBox).toHaveAttribute('open');
    await waitFor(() => {
      expect(document.activeElement).toHaveAttribute('id', 'turn-5');
    });
    expect(document.activeElement).toHaveTextContent('Question 3?');
    // The transcript shows the turn numbers the feedback cites.
    expect(within(transcriptBox).getByText('Turn 5')).toBeInTheDocument();
  });

  it('explains a degraded report, keeps the analysis, and asks the coach again', async () => {
    wrappedUp();
    let calls = 0;
    server.use(
      http.post('/api/sessions/:sessionId/feedback', () => {
        calls += 1;
        return HttpResponse.json(
          calls === 1 ? feedback({ degraded: true, report: null }) : feedback(),
        );
      }),
    );
    const { user } = await renderApp('/feedback/s1');

    const notice = await screen.findByRole('alert');
    expect(notice).toHaveTextContent("The AI coach isn't available right now");
    expect(notice).toHaveTextContent('still accurate');
    expect(screen.getByRole('table', { name: 'Discovery map' })).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: 'What went well' })).not.toBeInTheDocument();

    await user.click(within(notice).getByRole('button', { name: 'Ask the coach again' }));

    await screen.findByRole('heading', { level: 2, name: 'What went well' });
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it('shows an error with Try again when the request fails', async () => {
    wrappedUp();
    let calls = 0;
    server.use(
      http.post('/api/sessions/:sessionId/feedback', () => {
        calls += 1;
        return calls === 1 ? apiError('INTERNAL_ERROR', 500) : HttpResponse.json(feedback());
      }),
    );
    const { user } = await renderApp('/feedback/s1');

    const alert = await screen.findByRole('alert');
    expect(alert).toHaveTextContent('Something went wrong on the server.');
    await user.click(within(alert).getByRole('button', { name: 'Try again' }));

    await screen.findByRole('heading', { level: 2, name: 'Discovery map' });
  });

  it('starts a new interview with the same client', async () => {
    wrappedUp();
    let body: unknown;
    server.use(
      http.post('/api/sessions', async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(created(sara, 's2'), { status: 201 });
      }),
    );
    const { user, router } = await renderApp('/feedback/s1');

    await user.click(await screen.findByRole('button', { name: 'Try again with this client' }));

    await waitFor(() => {
      expect(router.state.location.pathname).toBe('/interview/s2');
    });
    expect(body).toEqual({ client_id: 'sara-test', language: 'en' });
  });

  it('offers another client and the Markdown download', async () => {
    wrappedUp();
    await renderApp('/feedback/s1');

    expect(await screen.findByRole('link', { name: 'Choose another client' })).toHaveAttribute(
      'href',
      '/',
    );
    const download = screen.getByRole('link', { name: 'Download transcript (.md)' });
    expect(download).toHaveAttribute('href', '/api/sessions/s1/export?format=md');
    expect(download).toHaveAttribute('download');
  });

  it('shows the full client profile behind the scenes', async () => {
    wrappedUp();
    const { user } = await renderApp('/feedback/s1');

    await user.click(await screen.findByText('Behind the scenes: the full client profile'));

    const profile = present(
      screen.getByText('Behind the scenes: the full client profile').closest('details'),
    );
    const factLine = (fact: string) =>
      present(within(profile).getByText(fact).parentElement).nextElementSibling;
    expect(profile).toHaveAttribute('open');
    expect(within(profile).getByText('Customers pay 90 days late.')).toBeInTheDocument();
    expect(factLine('A big order is coming.')).toHaveTextContent('Important · Not found');
    expect(factLine('Uses only Sharia-compliant products.')).toHaveTextContent(
      'in reaction to a product you proposed',
    );
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
