import { useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, Outlet, useOutletContext } from 'react-router';
import { useBank } from '../api/hooks';
import type { SessionModels } from '../api/types';
import { currentLanguage } from '../i18n';
import { localize } from '../i18n/format';
import { LanguageToggle } from './LanguageToggle';
import { SkipLink } from './SkipLink';

interface ShellContext {
  setSessionModels: (models: SessionModels | null) => void;
}

const MODEL_ROLES = ['client', 'gate', 'coach'] as const;

/** Every page's frame: skip link, header (bank name and language), <main>, and a footer with
 * the disclaimer and, during a session, its models. */
export function AppShell() {
  const { t } = useTranslation();
  const language = currentLanguage();
  const bank = useBank();
  const [models, setModels] = useState<SessionModels | null>(null);
  const context = useMemo<ShellContext>(() => ({ setSessionModels: setModels }), []);

  return (
    <div className="flex min-h-screen flex-col">
      <SkipLink />
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3 sm:px-6">
          {bank.status === 'loading' ? (
            <span className="min-h-11" />
          ) : (
            <Link
              to="/"
              className="inline-flex min-h-11 items-center rounded-sm text-xl font-semibold text-brand hover:text-brand-strong"
            >
              {bank.status === 'ready' ? localize(bank.data.name, language) : t('common.appName')}
            </Link>
          )}
          <LanguageToggle />
        </div>
      </header>

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 px-4 py-8 sm:px-6">
        <Outlet context={context} />
      </main>

      <footer className="border-t border-line bg-surface">
        <div className="mx-auto max-w-6xl space-y-2 px-4 py-5 text-sm text-ink-muted sm:px-6">
          {bank.status === 'ready' && <p>{localize(bank.data.disclaimer, language)}</p>}
          {models && (
            <div className="flex flex-wrap gap-x-4 gap-y-1">
              <span className="font-medium text-ink">{t('common.models')}</span>
              <dl className="flex flex-wrap gap-x-4 gap-y-1">
                {MODEL_ROLES.map((role) => (
                  <div key={role} className="flex gap-1.5">
                    <dt>{t(`common.modelRole.${role}`)}</dt>
                    <dd className="font-medium text-ink">
                      <bdi>{models[role]}</bdi>
                    </dd>
                  </div>
                ))}
              </dl>
            </div>
          )}
        </div>
      </footer>
    </div>
  );
}

/** Shows the session's models in the footer while the calling page is on screen. */
export function useSessionModels(models: SessionModels | undefined): void {
  const { setSessionModels } = useOutletContext<ShellContext>();
  useEffect(() => {
    if (!models) return;
    setSessionModels(models);
    return () => {
      setSessionModels(null);
    };
  }, [models, setSessionModels]);
}
