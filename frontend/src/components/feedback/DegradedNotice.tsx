import { useTranslation } from 'react-i18next';
import { InfoIcon } from '../icons';
import { secondaryButton } from '../styles';

interface DegradedNoticeProps {
  onRetry: () => void;
  retrying: boolean;
}

/** The coach was unavailable: say so, say the analysis still stands, and offer to try again.
 * Announced as it appears, like an error, but calm: this isn't the student's mistake. */
export function DegradedNotice({ onRetry, retrying }: DegradedNoticeProps) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="flex flex-col gap-3 rounded-md border border-line-strong bg-surface-sunken p-4 text-ink sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex gap-2">
        <InfoIcon className="mt-1 size-5 text-ink-muted" />
        <div>
          <p className="font-semibold">{t('feedback.degraded.title')}</p>
          <p>{t('feedback.degraded.body')}</p>
        </div>
      </div>
      <button
        type="button"
        onClick={() => {
          if (!retrying) onRetry();
        }}
        aria-disabled={retrying || undefined}
        className={`${secondaryButton} shrink-0`}
      >
        {retrying ? t('feedback.degraded.retrying') : t('feedback.degraded.retry')}
      </button>
    </div>
  );
}
