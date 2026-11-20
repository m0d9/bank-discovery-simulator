import 'i18next';
import type en from '../locales/en.json';

// Type every t() call against en.json, so a missing or misspelt key fails tsc.
declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'translation';
    resources: { translation: typeof en };
  }
}
