import { screen, waitFor } from '@testing-library/react';
import { axe } from 'jest-axe';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import type { Language } from './i18n';
import { feedback, session, transcript } from './test/fixtures';
import { setWideScreen } from './test/media';
import { renderApp } from './test/render';
import { server } from './test/server';

/** Each page with its data mocked, and what to wait for before checking it. */
const PAGES = [
  { page: 'client list', path: '/', ready: () => screen.findAllByRole('article') },
  { page: 'interview', path: '/interview/s1', ready: () => screen.findByRole('log') },
  {
    page: 'interview (wide layout)',
    path: '/interview/s1',
    wide: true,
    ready: () => screen.findByRole('log'),
  },
  { page: 'wrap-up', path: '/wrapup/s1', ready: () => screen.findAllByRole('checkbox') },
  {
    page: 'feedback',
    path: '/feedback/s1',
    status: 'wrapped_up' as const,
    ready: () => screen.findAllByRole('heading', { level: 2 }),
  },
  {
    page: 'feedback (transcript and profile open)',
    path: '/feedback/s1',
    status: 'feedback_ready' as const,
    ready: async () => {
      await screen.findAllByRole('heading', { level: 2 });
      for (const details of document.querySelectorAll('details')) details.open = true;
      await screen.findByRole('heading', { level: 3, name: /Persona|الملف الشخصي/ });
    },
  },
  {
    page: 'feedback (coach unavailable)',
    path: '/feedback/s1',
    status: 'wrapped_up' as const,
    feedback: () => HttpResponse.json(feedback({ degraded: true, report: null })),
    ready: () => screen.findByRole('alert'),
  },
  {
    page: 'feedback (the coach is writing)',
    path: '/feedback/s1',
    status: 'wrapped_up' as const,
    feedback: () => new Promise<never>(() => {}),
    ready: () => screen.findByText(/The coach is reviewing|يراجع المدرّب/),
  },
  { page: 'not found', path: '/nowhere', ready: () => screen.findByRole('heading', { level: 1 }) },
];

const LANGUAGES: Language[] = ['en', 'ar'];

describe.each(LANGUAGES)('accessibility (%s)', (language) => {
  it.each(PAGES)('the $page page has no axe violations', async (entry) => {
    const { path, wide, status, ready } = entry;
    setWideScreen(wide ?? false);
    server.use(
      http.get('/api/sessions/:sessionId', () =>
        HttpResponse.json(session({ turns: transcript(3), status: status ?? 'interviewing' })),
      ),
    );
    if (entry.feedback) server.use(http.post('/api/sessions/:sessionId/feedback', entry.feedback));
    await renderApp(path, { language });
    await ready();
    // Wait until the shell has its data too, so nothing changes while axe runs.
    await waitFor(() => {
      expect(screen.getByRole('contentinfo')).not.toBeEmptyDOMElement();
    });
    expect(document.documentElement).toHaveAttribute('lang', language);

    const results = await axe(document.body);
    const problems = results.violations.map(
      (violation) => `${violation.id}: ${violation.help} (${String(violation.nodes.length)})`,
    );
    expect(problems).toEqual([]);
  });
});
