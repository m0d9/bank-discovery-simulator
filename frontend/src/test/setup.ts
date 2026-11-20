import '@testing-library/jest-dom/vitest';
import { cleanup } from '@testing-library/react';
import { afterAll, afterEach, beforeAll, beforeEach } from 'vitest';
import { matchMedia, setWideScreen } from './media';
import { server } from './server';

// jsdom lacks these; the real behaviour is checked in a browser.
if (typeof window !== 'undefined') {
  window.matchMedia = matchMedia;
  const element = Element.prototype as Partial<Element>;
  if (typeof element.scrollIntoView !== 'function') {
    Element.prototype.scrollIntoView = () => undefined;
  }
  const dialog = HTMLDialogElement.prototype as Partial<HTMLDialogElement>;
  if (typeof dialog.showModal !== 'function') {
    HTMLDialogElement.prototype.showModal = function showModal(this: HTMLDialogElement) {
      this.setAttribute('open', '');
    };
    HTMLDialogElement.prototype.close = function close(this: HTMLDialogElement) {
      this.removeAttribute('open');
      this.dispatchEvent(new Event('close'));
    };
  }
}

beforeAll(() => {
  server.listen({ onUnhandledFrame: 'error' });
});

beforeEach(async () => {
  setWideScreen(false);
  // Files that opt into the node environment (no DOM) don't load the app's i18n.
  if (typeof document === 'undefined') return;
  const { default: i18n } = await import('../i18n');
  localStorage.clear();
  document.title = '';
  await i18n.changeLanguage('en');
});

afterEach(() => {
  cleanup();
  server.resetHandlers();
});

afterAll(() => {
  server.close();
});
