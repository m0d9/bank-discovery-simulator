import { useTranslation } from 'react-i18next';
import type { ClientCard as ClientCardData } from '../api/types';
import { currentLanguage } from '../i18n';
import { localize } from '../i18n/format';
import { Badge } from './Badge';
import { card, primaryButton } from './styles';

interface ClientCardProps {
  client: ClientCardData;
  /** This card's interview is being created. */
  starting: boolean;
  /** Another interview is being created: clicks are ignored, but the button keeps focus. */
  busy: boolean;
  onStart: (client: ClientCardData) => void;
}

export function ClientCard({ client, starting, busy, onStart }: ClientCardProps) {
  const { t } = useTranslation();
  const language = currentLanguage();
  const name = localize(client.name, language);
  const headingId = `client-${client.id}`;

  return (
    <article aria-labelledby={headingId} className={`${card} flex h-full flex-col gap-4 p-6`}>
      <div>
        <h2 id={headingId} className="text-xl font-semibold text-ink">
          {name}
        </h2>
        <p className="mt-1 text-ink-muted">{localize(client.headline, language)}</p>
      </div>
      <ul className="flex flex-wrap gap-2">
        <li>
          <Badge>{t(`common.segment.${client.segment}`)}</Badge>
        </li>
        <li>
          <Badge>
            {t('common.difficultyLabel', { level: t(`common.difficulty.${client.difficulty}`) })}
          </Badge>
        </li>
      </ul>
      <button
        type="button"
        aria-disabled={busy || undefined}
        onClick={() => {
          if (!busy) onStart(client);
        }}
        className={`${primaryButton} mt-auto w-full`}
      >
        {starting ? t('select.starting') : t('select.start', { name })}
      </button>
    </article>
  );
}
