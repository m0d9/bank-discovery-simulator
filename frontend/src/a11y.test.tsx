import { screen, waitFor } from '@testing-library/react';
import type { UserEvent } from '@testing-library/user-event';
import { axe } from 'jest-axe';
import { http, HttpResponse } from 'msw';
import { describe, expect, it } from 'vitest';
import type { Language } from './i18n';
import ar from './locales/ar.json';
import en from './locales/en.json';
import { feedback, healthDown, session, transcript } from './test/fixtures';
import { setWideScreen } from './test/media';
import { renderApp } from './test/render';
import { apiError, server } from './test/server';

const STRINGS = { en, ar } as const;
type Strings = (typeof STRINGS)[Language];

interface PageState {
  page: string;
  path: string;
  wide?: boolean;
  status?: 'interviewing' | 'wrapped_up' | 'feedback_ready';
  feedback?: () => Response | Promise<Response>;
  /** API behaviour this state needs on top of the defaults. */
  setup?: () => void;
  /** Waits for the state, first doing what brings it about (opening a dialog…). */
  ready: (user: UserEvent, strings: Strings) => Promise<unknown>;
}

/** Each page and key state with its data mocked, and what to wait for before checking it. */
const PAGES: PageState[] = [
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
  {
    page: 'client list (loading)',
    path: '/',
    setup: () => {
      server.use(http.get('/api/clients', () => new Promise<never>(() => {})));
    },
    ready: (_user, strings) => screen.findByText(strings.select.loading),
  },
  {
    page: 'client list (failed to load)',
    path: '/',
    setup: () => {
      server.use(http.get('/api/clients', () => apiError('INTERNAL_ERROR', 500)));
    },
    ready: () => screen.findByRole('alert'),
  },
  {
    page: 'model unreachable (health banner, details open)',
    path: '/',
    setup: () => {
      server.use(http.get('/api/health', () => HttpResponse.json(healthDown())));
    },
    ready: async (user, strings) => {
      await screen.findAllByRole('article');
      await user.click(await screen.findByText(strings.health.details));
      await screen.findByText(strings.health.unreachable);
    },
  },
  {
    page: 'interview (end dialog open)',
    path: '/interview/s1',
    ready: async (user, strings) => {
      await screen.findByRole('log');
      await user.click(screen.getByRole('button', { name: strings.interview.end }));
      await screen.findByRole('dialog');
    },
  },
  {
    page: 'wrap-up (errors shown)',
    path: '/wrapup/s1',
    ready: async (user, strings) => {
      await screen.findAllByRole('checkbox');
      await user.click(screen.getByRole('button', { name: strings.wrapup.submit }));
      await screen.findByRole('alert');
    },
  },
  {
    page: 'session lost',
    path: '/interview/s1',
    setup: () => {
      server.use(http.get('/api/sessions/:sessionId', () => apiError('SESSION_NOT_FOUND', 404)));
    },
    ready: (_user, strings) => screen.findByRole('link', { name: strings.common.startAgain }),
  },
];

const LANGUAGES: Language[] = ['en', 'ar'];

describe.each(LANGUAGES)('accessibility (%s)', (language) => {
  it.each(PAGES)('the $page page has no axe violations', async (entry) => {
    const { path, wide, status, ready, setup } = entry;
    setWideScreen(wide ?? false);
    server.use(
      http.get('/api/sessions/:sessionId', () =>
        HttpResponse.json(session({ turns: transcript(3), status: status ?? 'interviewing' })),
      ),
    );
    if (entry.feedback) server.use(http.post('/api/sessions/:sessionId/feedback', entry.feedback));
    setup?.();
    const { user } = await renderApp(path, { language });
    await ready(user, STRINGS[language]);
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
