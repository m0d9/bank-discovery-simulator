import { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router';
import { type ApiError, createSession, toApiError } from '../api/client';
import { useClients } from '../api/hooks';
import type { ClientCard as ClientCardData } from '../api/types';
import { ClientCard } from '../components/ClientCard';
import { ErrorBanner } from '../components/ErrorBanner';
import { PageHeading } from '../components/PageHeading';
import { currentLanguage } from '../i18n';

export function ClientSelectPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const clients = useClients();
  const [starting, setStarting] = useState<string | null>(null);
  const [failed, setFailed] = useState<{ client: ClientCardData; error: ApiError } | null>(null);

  async function start(client: ClientCardData) {
    setStarting(client.id);
    setFailed(null);
    try {
      // The interview starts in the language the UI is in now.
      const session = await createSession(client.id, currentLanguage());
      await navigate(`/interview/${session.session_id}`);
    } catch (cause) {
      setFailed({ client, error: toApiError(cause) });
      setStarting(null);
    }
  }

  return (
    <>
      <PageHeading title={t('select.title')} />
      <p className="mt-3 max-w-prose text-lg text-ink-muted">{t('select.intro')}</p>

      {failed && (
        <div className="mt-6">
          <ErrorBanner error={failed.error} onRetry={() => void start(failed.client)} />
        </div>
      )}

      <div className="mt-8">
        {clients.status === 'loading' && (
          <p role="status" className="text-ink-muted">
            {t('select.loading')}
          </p>
        )}
        {clients.status === 'error' && (
          <ErrorBanner error={clients.error} onRetry={clients.reload} />
        )}
        {clients.status === 'ready' &&
          (clients.data.length === 0 ? (
            <p className="text-ink-muted">{t('select.empty')}</p>
          ) : (
            <ul className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
              {clients.data.map((client) => (
                <li key={client.id}>
                  <ClientCard
                    client={client}
                    starting={starting === client.id}
                    busy={starting !== null}
                    onStart={(chosen) => void start(chosen)}
                  />
                </li>
              ))}
            </ul>
          ))}
      </div>
    </>
  );
}
