import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { ApiError } from '../api/client';
import { ErrorBanner } from './ErrorBanner';
import { secondaryButton } from './styles';

/** The session has expired or the app restarted: explain, and offer a fresh start. */
export function SessionLost() {
  const { t } = useTranslation();
  return (
    <ErrorBanner error={new ApiError('SESSION_NOT_FOUND')}>
      <Link to="/" className={secondaryButton}>
        {t('common.startAgain')}
      </Link>
    </ErrorBanner>
  );
}

/** Errors that sending again can't fix. */
const FINAL_CODES = new Set(['SESSION_NOT_FOUND', 'INVALID_INPUT', 'TURN_LIMIT', 'INVALID_STATE']);

export function canRetry(error: ApiError): boolean {
  return !FINAL_CODES.has(error.code);
}
