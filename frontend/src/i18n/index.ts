import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import ar from '../locales/ar.json';
import en from '../locales/en.json';

export const LANGUAGES = ['en', 'ar'] as const;
export type Language = (typeof LANGUAGES)[number];

/** The only thing the app stores in the browser. */
const STORAGE_KEY = 'lang';

function isLanguage(value: unknown): value is Language {
  return value === 'en' || value === 'ar';
}

function savedLanguage(): Language | null {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    return isLanguage(saved) ? saved : null;
  } catch {
    // Storage can be blocked (privacy settings); fall through to the browser language.
    return null;
  }
}

/** The saved choice, then the browser's languages in order of preference, then English. */
export function detectLanguage(): Language {
  const saved = savedLanguage();
  if (saved) return saved;
  for (const tag of navigator.languages) {
    const base = tag.split('-')[0]?.toLowerCase();
    if (isLanguage(base)) return base;
  }
  return 'en';
}

/** The UI language now: `en` or `ar`. */
export function currentLanguage(): Language {
  return isLanguage(i18n.language) ? i18n.language : 'en';
}

export function otherLanguage(language: Language): Language {
  return language === 'ar' ? 'en' : 'ar';
}

/** Switch the UI language and remember the choice. */
export async function setLanguage(language: Language): Promise<void> {
  try {
    localStorage.setItem(STORAGE_KEY, language);
  } catch {
    // Without storage the choice lasts until the page is reloaded.
  }
  await i18n.changeLanguage(language);
}

function applyToDocument(language: string): void {
  document.documentElement.lang = language;
  document.documentElement.dir = i18n.dir(language);
}

i18n.on('languageChanged', applyToDocument);

void i18n.use(initReactI18next).init({
  resources: { en: { translation: en }, ar: { translation: ar } },
  lng: detectLanguage(),
  fallbackLng: 'en',
  supportedLngs: [...LANGUAGES],
  // React escapes text itself.
  interpolation: { escapeValue: false },
  // The resources are bundled, so the first render already has every string.
  initAsync: false,
});
applyToDocument(i18n.language);

export default i18n;
