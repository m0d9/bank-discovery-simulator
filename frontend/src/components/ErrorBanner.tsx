import type { ReactNode } from 'react';
import { useTranslation } from 'react-i18next';
import type { ApiError } from '../api/client';
import { errorMessage } from '../i18n/errors';
import { AlertIcon } from './icons';
import { secondaryButton } from './styles';

interface ErrorBannerProps {
  error: ApiError;
  /** Shows a Retry button when given. */
  onRetry?: () => void;
  /** Extra actions, such as a "Start again" link. */
  children?: ReactNode;
}

/** A failed request, announced as it appears (`role="alert"`). The icon and the words carry
 * the meaning; the red border only adds to them. */
export function ErrorBanner({ error, onRetry, children }: ErrorBannerProps) {
  const { t } = useTranslation();
  return (
    <div
      role="alert"
      className="flex flex-col gap-3 rounded-md border border-danger bg-danger-tint p-4 text-ink sm:flex-row sm:items-center sm:justify-between"
    >
      <p className="flex gap-2">
        <AlertIcon className="mt-1 size-5 text-danger" />
        <span>{errorMessage(t, error)}</span>
      </p>
      {(onRetry ?? children) && (
        <div className="flex shrink-0 flex-wrap items-center gap-3">
          {onRetry && (
            <button type="button" onClick={onRetry} className={secondaryButton}>
              {t('common.retry')}
            </button>
          )}
          {children}
        </div>
      )}
    </div>
  );
}
