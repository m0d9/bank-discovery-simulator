import { useTranslation } from 'react-i18next';
import type { LocalizedText } from '../api/types';
import { currentLanguage } from '../i18n';
import { localize } from '../i18n/format';

interface ContentTextProps {
  text: LocalizedText;
  className?: string;
}

/** Content in the UI language. Where the content has no Arabic, the English stands in,
 * marked as English so a screen reader switches voice and the text keeps its direction. */
export function ContentText({ text, className }: ContentTextProps) {
  useTranslation(); // re-render when the language changes
  const language = currentLanguage();
  const fallback = language === 'ar' && !text.ar;
  return (
    <span
      className={className}
      lang={fallback ? 'en' : undefined}
      dir={fallback ? 'ltr' : undefined}
    >
      {localize(text, language)}
    </span>
  );
}
