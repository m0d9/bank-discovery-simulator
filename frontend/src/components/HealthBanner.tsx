import { useTranslation } from 'react-i18next';
import { useHealth } from '../api/hooks';
import type { Health } from '../api/types';
import { AlertIcon, ChevronDownIcon } from './icons';
import { secondaryButton } from './styles';

const MODEL_ROLES = ['client', 'gate', 'coach'] as const;

/** Says so when the AI model can't be used (`/api/health` is down or degraded): what's wrong
 * and what to check, in the UI language, with Retry and the technical details folded away.
 * The polite live region is always there, so the notice is announced when it appears without
 * interrupting anything. */
export function HealthBanner() {
  const { t } = useTranslation();
  const { health, checking, recheck } = useHealth();
  const problem = health && health.status !== 'ok' ? health : null;

  return (
    <div role="status">
      {problem && (
        <div className="mb-6 flex flex-col gap-3 rounded-md border border-attention bg-attention-tint p-4 text-ink sm:flex-row sm:items-start sm:justify-between">
          <div className="flex gap-2">
            <AlertIcon className="mt-1 size-5 shrink-0 text-attention" />
            <div className="space-y-1">
              <p className="font-semibold">
                {problem.status === 'down' ? t('health.down') : t('health.degraded')}
              </p>
              {problem.hint_code && <p>{t(`health.${problem.hint_code}`)}</p>}
              <HealthDetails health={problem} />
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              if (!checking) recheck();
            }}
            aria-disabled={checking || undefined}
            className={`${secondaryButton} shrink-0`}
          >
            {checking ? t('health.checking') : t('common.retry')}
          </button>
        </div>
      )}
    </div>
  );
}

/** The endpoint, each role's model and the server's own (English) hint, for whoever runs the
 * app. Host and model names are isolated so they read correctly in Arabic. */
function HealthDetails({ health }: { health: Health }) {
  const { t } = useTranslation();
  const { endpoint, models, hint } = health;
  return (
    <details className="group">
      <summary className="inline-flex min-h-11 cursor-pointer list-none items-center gap-1 rounded-sm font-medium text-ink underline underline-offset-4 [&::-webkit-details-marker]:hidden">
        {t('health.details')}
        <ChevronDownIcon className="size-5 group-open:rotate-180" />
      </summary>
      <dl className="space-y-1 text-sm">
        <div className="flex flex-wrap gap-x-2">
          <dt className="font-medium">{t('health.endpoint')}</dt>
          <dd className="flex flex-wrap gap-x-2">
            <bdi>{endpoint.host}</bdi>
            <span>{endpoint.reachable ? t('health.reachable') : t('health.unreachable')}</span>
          </dd>
        </div>
        {MODEL_ROLES.map((role) => (
          <div key={role} className="flex flex-wrap gap-x-2">
            <dt className="font-medium">{t(`common.modelRole.${role}`)}</dt>
            <dd className="flex flex-wrap gap-x-2">
              <bdi>{models[role].name}</bdi>
              <span>{models[role].available ? t('health.available') : t('health.missing')}</span>
            </dd>
          </div>
        ))}
        {hint && (
          <div className="flex flex-wrap gap-x-2">
            <dt className="font-medium">{t('health.serverMessage')}</dt>
            <dd lang="en" dir="ltr">
              {hint}
            </dd>
          </div>
        )}
      </dl>
    </details>
  );
}
