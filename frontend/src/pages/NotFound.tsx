import { useTranslation } from 'react-i18next';
import { Link } from 'react-router';
import { PageHeading } from '../components/PageHeading';
import { textLink } from '../components/styles';

export function NotFound() {
  const { t } = useTranslation();
  return (
    <div className="max-w-prose">
      <PageHeading title={t('common.notFound.title')} />
      <p className="mt-3 text-ink-muted">{t('common.notFound.body')}</p>
      <p className="mt-6">
        <Link to="/" className={textLink}>
          {t('common.home')}
        </Link>
      </p>
    </div>
  );
}
