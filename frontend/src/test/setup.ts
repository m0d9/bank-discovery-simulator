import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterEach, beforeEach } from 'vitest';

beforeEach(async () => {
  // Files that opt into the node environment (no DOM) don't load the app's i18n.
  if (typeof document === 'undefined') return;
  const { default: i18n } = await import('../i18n');
  localStorage.clear();
  await i18n.changeLanguage('en');
});

afterEach(() => {
  cleanup();
});
