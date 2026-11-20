import type { LocalizedText } from '../api/types';
import type { Language } from './index';

/** Content text in the UI language. Content may lack Arabic (`null`), so English stands in. */
export function localize(text: LocalizedText, language: Language): string {
  return language === 'ar' && text.ar ? text.ar : text.en;
}

const NUMBER_LOCALES: Record<Language, string> = {
  en: 'en',
  // Western digits in Arabic too, with the usual grouping: 1,000.
  ar: 'ar-u-nu-latn',
};

export function formatNumber(value: number, language: Language): string {
  return new Intl.NumberFormat(NUMBER_LOCALES[language]).format(value);
}

/** The student's text as the server counts it: control characters removed (newlines and tabs
 * kept), trimmed, then counted in code points rather than UTF-16 units. */
export function countChars(text: string): number {
  const cleaned = text
    .replace(/\r\n?/g, '\n')
    .replace(/\p{Cc}/gu, (char) => (char === '\n' || char === '\t' ? char : ''))
    .trim();
  // Code points, like Python's len(): an emoji made of several code points counts as several.
  return Array.from(cleaned).length;
}

/** The length the server checks for the wrap-up fields: trimmed, in code points. */
export function trimmedLength(text: string): number {
  return Array.from(text.trim()).length;
}
