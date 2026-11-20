import { useTranslation } from 'react-i18next';
import { textLink } from './styles';

/** Shown instead of the router's developer page if rendering a page throws. */
export function RouteError() {
  const { t } = useTranslation();
  return (
    <main id="main" className="mx-auto max-w-prose px-4 py-12">
      <h1 className="text-2xl font-semibold text-ink">{t('errors.GENERIC')}</h1>
      <p className="mt-6">
        {/* A full page load, so the app starts afresh. */}
        <a href="/" className={textLink}>
          {t('common.home')}
        </a>
      </p>
    </main>
  );
}
