import { render } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createMemoryRouter, RouterProvider } from 'react-router';
import i18n, { type Language } from '../i18n';
import { routes } from '../router';

interface Options {
  language?: Language;
}

/** Render the whole app (shell and routes) at `path`, with the API mocked by msw. */
export async function renderApp(path: string, { language = 'en' }: Options = {}) {
  await i18n.changeLanguage(language);
  const router = createMemoryRouter(routes, { initialEntries: [path] });
  const user = userEvent.setup();
  const view = render(<RouterProvider router={router} />);
  return { ...view, router, user };
}
