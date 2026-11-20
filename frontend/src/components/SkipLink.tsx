import type { MouseEvent } from 'react';
import { useTranslation } from 'react-i18next';

/** The first stop on every page: moves focus past the header to <main>. */
export function SkipLink() {
  const { t } = useTranslation();

  // Focus <main> directly: following "#main" would add a history entry the router would see.
  function skip(event: MouseEvent<HTMLAnchorElement>) {
    event.preventDefault();
    document.getElementById('main')?.focus();
  }

  return (
    <a
      href="#main"
      onClick={skip}
      className="sr-only focus:not-sr-only focus:absolute focus:start-4 focus:top-4 focus:z-50 focus:rounded-md focus:bg-surface focus:px-4 focus:py-3 focus:font-semibold focus:text-brand focus:shadow-md"
    >
      {t('common.skipLink')}
    </a>
  );
}
