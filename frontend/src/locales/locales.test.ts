import { describe, expect, it } from 'vitest';
import errorCodes from '../api/error-codes.json';
import openapi from '../api/openapi.json';
import ar from './ar.json';
import en from './en.json';

const LOCALES = { en, ar } as const;
/** The codes `/api/health` can send as `hint_code`, from the API contract. */
const HINT_CODES = openapi.components.schemas.HealthDTO.properties.hint_code.anyOf.flatMap(
  (option) => option.enum ?? [],
);
const PLURAL_SUFFIX = /_(zero|one|two|few|many|other)$/;
/** Codes the browser produces itself (`src/api/client.ts`), on top of the API's. */
const FRONTEND_CODES = ['GENERIC', 'NETWORK'];

function flatten(value: unknown, prefix = ''): Map<string, unknown> {
  const out = new Map<string, unknown>();
  if (typeof value === 'object' && value !== null) {
    for (const [key, child] of Object.entries(value)) {
      for (const [path, leaf] of flatten(child, prefix ? `${prefix}.${key}` : key)) {
        out.set(path, leaf);
      }
    }
  } else {
    out.set(prefix, value);
  }
  return out;
}

/** Each key without its plural suffix, with the plural forms it has. */
function baseKeys(locale: object): Map<string, Set<string>> {
  const bases = new Map<string, Set<string>>();
  for (const key of flatten(locale).keys()) {
    const match = PLURAL_SUFFIX.exec(key);
    const base = match ? key.slice(0, match.index) : key;
    const forms = bases.get(base) ?? new Set<string>();
    if (match?.[1]) forms.add(match[1]);
    bases.set(base, forms);
  }
  return bases;
}

describe('locale files', () => {
  it('have the same keys, apart from plural forms', () => {
    expect([...baseKeys(ar).keys()].sort()).toEqual([...baseKeys(en).keys()].sort());
  });

  it.each(Object.entries(LOCALES))(
    '%s has every plural form its language needs, and no others',
    (language, locale) => {
      const needed = new Intl.PluralRules(language).resolvedOptions().pluralCategories;
      for (const [key, forms] of baseKeys(locale)) {
        if (forms.size === 0) continue;
        expect([...forms].sort(), key).toEqual([...needed].sort());
      }
    },
  );

  it.each(Object.entries(LOCALES))('%s has no empty or non-string values', (_language, locale) => {
    for (const [key, value] of flatten(locale)) {
      expect(typeof value === 'string' && value.trim() !== '', key).toBe(true);
    }
  });

  it.each(Object.entries(LOCALES))(
    '%s has errors.<CODE> for every API error code and the frontend codes',
    (_language, locale) => {
      const keys = flatten(locale);
      for (const code of [...errorCodes, ...FRONTEND_CODES]) {
        expect(keys.has(`errors.${code}`), code).toBe(true);
      }
    },
  );

  it.each(Object.entries(LOCALES))(
    '%s has health.<CODE> for every hint code /api/health can send',
    (_language, locale) => {
      const keys = flatten(locale);
      expect(HINT_CODES.length).toBeGreaterThan(0);
      for (const code of HINT_CODES) {
        expect(keys.has(`health.${code}`), code).toBe(true);
      }
    },
  );
});
