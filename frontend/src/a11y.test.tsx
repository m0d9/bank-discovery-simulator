import { screen, waitFor } from '@testing-library/react';
import { axe } from 'jest-axe';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import type { Language } from './i18n';
import { session, transcript } from './test/fixtures';
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
    ready: () => screen.findAllByRole('link', { name: /.+/ }),
  },
  { page: 'not found', path: '/nowhere', ready: () => screen.findByRole('heading', { level: 1 }) },
];

const LANGUAGES: Language[] = ['en', 'ar'];

describe.each(LANGUAGES)('accessibility (%s)', (language) => {
  it.each(PAGES)('the $page page has no axe violations', async ({ path, wide, status, ready }) => {
    setWideScreen(wide ?? false);
    server.use(
      http.get('/api/sessions/:sessionId', () =>
        HttpResponse.json(session({ turns: transcript(3), status: status ?? 'interviewing' })),
      ),
    );
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
