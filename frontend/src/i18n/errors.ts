import type { TFunction } from 'i18next';
import type { ApiError } from '../api/client';
import en from '../locales/en.json';

type ErrorCode = keyof typeof en.errors;

function isErrorCode(code: string): code is ErrorCode {
  return Object.hasOwn(en.errors, code);
}

/** The localized message for an `ApiError`, from its `messageKey` (`errors.<CODE>`). A code
 * the UI doesn't know shows the generic message. */
export function errorMessage(t: TFunction, error: ApiError): string {
  const code = error.messageKey.replace(/^errors\./, '');
  return t(`errors.${isErrorCode(code) ? code : 'GENERIC'}`);
}
