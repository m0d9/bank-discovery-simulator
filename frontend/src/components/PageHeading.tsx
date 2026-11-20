import { type ReactNode, useEffect, useRef } from 'react';
import { useTranslation } from 'react-i18next';
import { useLocation } from 'react-router';

interface PageHeadingProps {
  /** The page's name, also used for the document title. */
  title: string;
  /** Richer heading content, if it differs from `title`. */
  children?: ReactNode;
}

/** The page's <h1>. It sets the localized document title and, after a navigation inside the
 * app (not on the first load), takes focus so screen readers start at the new page. */
export function PageHeading({ title, children }: PageHeadingProps) {
  const { t } = useTranslation();
  const ref = useRef<HTMLHeadingElement>(null);
  const arrivedByNavigation = useLocation().key !== 'default';

  useEffect(() => {
    document.title = t('common.documentTitle', { page: title, app: t('common.appName') });
  }, [t, title]);

  useEffect(() => {
    if (arrivedByNavigation) ref.current?.focus();
  }, [arrivedByNavigation]);

  return (
    <h1 ref={ref} tabIndex={-1} className="text-2xl font-semibold text-ink sm:text-3xl">
      {children ?? title}
    </h1>
  );
}
