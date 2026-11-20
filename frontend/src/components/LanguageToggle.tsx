import { useTranslation } from 'react-i18next';
import { currentLanguage, otherLanguage, setLanguage } from '../i18n';
import { GlobeIcon } from './icons';

/** Switches between English and Arabic. The label is the other language's own name, marked
 * with its `lang` so screen readers pronounce it correctly. */
export function LanguageToggle() {
  const { t } = useTranslation();
  const target = otherLanguage(currentLanguage());
  return (
    <button
      type="button"
      onClick={() => void setLanguage(target)}
      className="inline-flex min-h-11 items-center gap-2 rounded-md border border-line-strong bg-surface px-3 text-sm font-medium text-ink hover:bg-surface-sunken"
    >
      <GlobeIcon />
      <span lang={target}>{t('common.languageName', { lng: target })}</span>
    </button>
  );
}
