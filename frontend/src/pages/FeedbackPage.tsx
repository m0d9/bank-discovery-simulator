import { useTranslation } from 'react-i18next';
import { Link, Navigate } from 'react-router';
import { useSession } from '../api/hooks';
import { useSessionModels } from '../components/AppShell';
import { ErrorBanner } from '../components/ErrorBanner';
import { InfoIcon } from '../components/icons';
import { PageHeading } from '../components/PageHeading';
import { SessionLost } from '../components/SessionLost';
import { card, primaryButton } from '../components/styles';
import { currentLanguage } from '../i18n';
import { localize } from '../i18n/format';

/** A placeholder until the AI coach arrives (M5). */
export function FeedbackPage({ sessionId }: { sessionId: string }) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const loaded = useSession(sessionId);
  const session = loaded.status === 'ready' ? loaded.data : undefined;
  useSessionModels(session?.models);

  // Nothing has been submitted yet: back to the interview.
  if (session?.status === 'interviewing') {
    return <Navigate to={`/interview/${sessionId}`} replace />;
  }

  const title = session
    ? t('feedback.titleWithName', { name: localize(session.client.name, language) })
    : t('feedback.title');

  return (
    <div className="max-w-2xl">
      <PageHeading title={title} />
      <div className="mt-6">
        {loaded.status === 'loading' && (
          <p role="status" className="text-ink-muted">
            {t('common.loading')}
          </p>
        )}
        {loaded.status === 'error' &&
          (loaded.error.code === 'SESSION_NOT_FOUND' ? (
            <SessionLost />
          ) : (
            <ErrorBanner error={loaded.error} onRetry={loaded.reload} />
          ))}
        {session && (
          <>
            <div className={`${card} flex gap-3 p-6`}>
              <InfoIcon className="mt-1 size-5 text-brand" />
              <p className="text-ink">{t('feedback.placeholder')}</p>
            </div>
            <p className="mt-8">
              <Link to="/" className={primaryButton}>
                {t('feedback.another')}
              </Link>
            </p>
          </>
        )}
      </div>
    </div>
  );
}
